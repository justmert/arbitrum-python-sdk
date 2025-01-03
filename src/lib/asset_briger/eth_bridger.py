from decimal import Decimal
from typing import Optional, Dict, Any

from web3 import Web3
from web3.types import Wei

from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.data_entities.constants import ARB_SYS_ADDRESS
from src.lib.data_entities.errors import MissingProviderArbSdkError
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.data_entities.transaction_request import (
    is_parent_to_child_transaction_request,
    is_child_to_parent_transaction_request,
)
from src.lib.message.parent_to_child_message_creator import ParentToChildMessageCreator
from src.lib.message.parent_transaction import ParentTransactionReceipt
from src.lib.message.child_transaction import ChildTransactionReceipt
from src.lib.utils.helper import (
    load_contract,
    get_native_token_decimals,
    scale_from_native_token_decimals_to_18_decimals,
    is_arbitrum_chain,
)
from src.lib.utils.eth import MAX_INT

class EthBridger(AssetBridger):
    def __init__(self, child_network):
        super().__init__(child_network)
        self.child_network = child_network

    @staticmethod
    async def from_provider(child_provider):
        return EthBridger(await get_arbitrum_network(child_provider))

    def is_approve_gas_token_params(self, params: Dict[str, Any]) -> bool:
        return 'txRequest' not in params

    def get_approve_gas_token_request(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        erc20_interface = load_contract(
            provider=params.get("parentProvider"),
            contract_name="ERC20",
            is_classic=True,
        )

        data = erc20_interface.encodeABI(
            fn_name="approve",
            args=[
                self.child_network.eth_bridge.inbox,
                params.get("amount", MAX_INT),
            ],
        )

        return {
            "to": self.native_token,
            "data": data,
            "value": 0,
        }

    async def approve_gas_token(self, params):
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        approve_gas_token_request = (
            self.get_approve_gas_token_request(params) if self.is_approve_gas_token_params(params)
            else params["txRequest"]
        )

        tx = {
            **approve_gas_token_request,
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        tx_hash = params["parentSigner"].provider.eth.send_transaction(tx)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def get_deposit_request_data(self, params):
        if not self.native_token_is_eth:
            erc20_inbox = load_contract(
                provider=params.get("parentProvider"),
                contract_name="ERC20Inbox",
                is_classic=True,
            )
            return erc20_inbox.encodeABI(
                fn_name="depositERC20",
                args=[params["amount"]],
            )

        inbox = load_contract(
            provider=params.get("parentProvider"),
            contract_name="Inbox",
            is_classic=False,
        )
        return inbox.encodeABI(fn_name="depositEth", args=[])

    async def get_deposit_request(self, params):
        return {
            "txRequest": {
                "to": self.child_network.eth_bridge.inbox,
                "value": params["amount"] if self.native_token_is_eth else 0,
                "data": self.get_deposit_request_data(params),
                "from": params["from"],
            },
            "isValid": lambda: True,
        }

    async def deposit(self, params):
        await self.check_parent_network(params["parentSigner"])

        eth_deposit = (
            params if is_parent_to_child_transaction_request(params)
            else await self.get_deposit_request({
                **params,
                "from": params["parentSigner"].account.address,
            })
        )

        tx = {
            **eth_deposit["txRequest"],
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        tx_hash = params["parentSigner"].provider.eth.send_transaction(tx)
        tx_receipt = params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_eth_deposit_wait(tx_receipt)

    async def get_deposit_to_request(self, params):
        decimals = await get_native_token_decimals({
            "parentProvider": params["parentProvider"],
            "childNetwork": self.child_network,
        })

        amount_to_be_minted_on_child_chain = scale_from_native_token_decimals_to_18_decimals(
            amount=params["amount"],
            decimals=decimals,
        )

        request_params = {
            **params,
            "to": params["destinationAddress"],
            "l2CallValue": amount_to_be_minted_on_child_chain,
            "callValueRefundAddress": params["destinationAddress"],
            "data": "0x",
        }
        gas_overrides = params.get("retryableGasOverrides", {})
        
        return await ParentToChildMessageCreator.get_ticket_creation_request(
            request_params, params["parentProvider"], params["childProvider"], gas_overrides
        )

    async def deposit_to(self, params):
        await self.check_parent_network(params["parentSigner"])
        await self.check_child_network(params["childProvider"])

        retryable_ticket_request = (
            params if is_parent_to_child_transaction_request(params)
            else await self.get_deposit_to_request({
                **params,
                "from": params["parentSigner"].account.address,
                "parentProvider": params["parentSigner"].provider,
            })
        )

        parent_to_child_message_creator = ParentToChildMessageCreator(params["parentSigner"])
        tx = await parent_to_child_message_creator.create_retryable_ticket(
            retryable_ticket_request, 
            params["childProvider"]
        )

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx)

    async def get_withdrawal_request(self, params):
        arb_sys = load_contract(
            provider=params.get("childProvider", params["childSigner"].provider),
            contract_name="ArbSys",
            address=ARB_SYS_ADDRESS,
            is_classic=False,
        )

        function_data = arb_sys.encodeABI(
            fn_name="withdrawEth",
            args=[params["destinationAddress"]],
        )

        async def estimate_parent_gas_limit(parent_provider):
            if await is_arbitrum_chain(parent_provider):
                # For L3, return higher gas estimate
                return 4_000_000
            # For L1, return regular estimate
            return 130000

        return {
            "txRequest": {
                "to": ARB_SYS_ADDRESS,
                "data": function_data,
                "value": params["amount"],
                "from": params["from"],
            },
            "estimateParentGasLimit": estimate_parent_gas_limit,
        }

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params["childSigner"]):
            raise MissingProviderArbSdkError("childSigner")

        await self.check_child_network(params["childSigner"])

        request = (
            params if is_child_to_parent_transaction_request(params)
            else await self.get_withdrawal_request(params)
        )

        tx = {
            **request["txRequest"],
            **params.get("overrides", {}),
            "from": params["childSigner"].account.address,
        }

        tx_hash = params["childSigner"].provider.eth.send_transaction(tx)
        tx_receipt = params["childSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ChildTransactionReceipt.monkey_patch_wait(tx_receipt)