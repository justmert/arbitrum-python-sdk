from typing import Optional, Dict, Any, Union

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
    """
    Bridger for moving ETH (or a custom gas token) between a Parent (L1) and Child (L2) network.
    Inherits base bridging checks from AssetBridger.
    """

    def __init__(self, child_network):
        """
        :param child_network: The network configuration object for the child chain (Arbitrum).
        """
        super().__init__(child_network)
        self.child_network = child_network

    @staticmethod
    async def from_provider(child_provider) -> "EthBridger":
        """
        Creates an EthBridger instance from a Web3 provider connected to the child chain.
        
        :param child_provider: A Web3 provider for the child chain (Arbitrum).
        :return: An EthBridger instance configured for that child network.
        """
        network = await get_arbitrum_network(child_provider)
        return EthBridger(network)

    def is_approve_gas_token_params(self, params: Dict[str, Any]) -> bool:
        """
        Helper function to distinguish between an ApproveGasTokenParams 
        dict and an ApproveGasTokenTxRequest dict.
        
        :param params: The dictionary describing either custom Tx or standard Approve params
        :return: True if the dictionary is standard ApproveGasTokenParams, 
                 False if it has 'txRequest' for a custom transaction.
        """
        return 'txRequest' not in params

    def get_approve_gas_token_request(
        self, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Creates a transaction request object to approve a custom gas token (ERC20)
        for bridging on the parent chain. If the chain actually uses ETH natively,
        calling this raises an error.
        
        :param params: Optionally, a dict with 'parentProvider' and 'amount' 
                       (defaults to MAX_INT if not provided).
        :return: A transaction request with fields: {"to", "data", "value"} 
        :raises ValueError: If the chain uses ETH natively (no token approval needed).
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        parent_provider = params.get("parentProvider") if params else None
        erc20_interface = load_contract(
            provider=parent_provider,
            contract_name="ERC20",
            is_classic=True,
        )
        amount = params.get("amount", MAX_INT) if params else MAX_INT

        data = erc20_interface.encodeABI(
            fn_name="approve",
            args=[
                self.child_network.eth_bridge.inbox,
                amount,
            ],
        )

        return {
            "to": self.native_token,
            "data": data,
            "value": 0,
        }

    async def approve_gas_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Approves the custom gas token to be spent by the Inbox on the parent network.
        If the network uses ETH natively, this is unnecessary and raises an error.
        
        :param params: A dict that may either define:
            - ApproveGasTokenParams {"amount", "parentSigner", ...}
            - or ApproveGasTokenTxRequest {"txRequest", "parentSigner", ...}
        :return: The transaction receipt from the parent chain.
        :raises ValueError: If the chain uses ETH natively.
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        # Distinguish whether we have a custom transaction or standard params
        if self.is_approve_gas_token_params(params):
            approve_req = self.get_approve_gas_token_request(params)
        else:
            approve_req = params["txRequest"]

        # Merge any overrides and set the 'from' address
        tx = {
            **approve_req,
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        tx_hash = params["parentSigner"].provider.eth.send_transaction(tx)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def get_deposit_request_data(self, params: Dict[str, Any]) -> bytes:
        """
        Constructs calldata for depositing either ETH or a custom gas token.
        
        :param params: A dict with optional 'parentProvider' and 'amount'.
        :return: Byte data for depositEth() if chain uses ETH, or depositERC20() if a custom token.
        """
        parent_provider = params.get("parentProvider")

        if not self.native_token_is_eth:
            erc20_inbox = load_contract(
                provider=parent_provider,
                contract_name="ERC20Inbox",
                is_classic=True,
            )
            return erc20_inbox.encodeABI(
                fn_name="depositERC20",
                args=[params["amount"]],
            )

        inbox = load_contract(
            provider=parent_provider,
            contract_name="Inbox",
            is_classic=False,
        )
        return inbox.encodeABI(fn_name="depositEth", args=[])

    async def get_deposit_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a transaction request for depositing ETH or a custom gas token directly 
        into the child's 'inbox' contract. 
        This is the simpler deposit scenario where tokens are minted for the same user 
        on the child chain.

        :param params: {
            "amount": int, 
            "from": str (the parent chain address sending),
            "parentProvider": Web3,
            ...
        }
        :return: A dict with:
          - "txRequest": {"to", "value", "data", "from"}
          - "isValid": a function (lambda) returning True
        """
        return {
            "txRequest": {
                "to": self.child_network.eth_bridge.inbox,
                "value": params["amount"] if self.native_token_is_eth else 0,
                "data": self.get_deposit_request_data(params),
                "from": params["from"],
            },
            "isValid": lambda: True,
        }

    async def deposit(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """
        Performs a deposit of ETH or custom gas token from the Parent chain to the Child chain 
        *to the same user address*. 
        If a transaction request is not already provided, builds one.
        
        :param params: Either an ErcDepositParams dict 
                       OR a ParentToChildTransactionRequest + "parentSigner" 
        :return: A ParentTransactionReceipt after the deposit is broadcast and mined on the parent chain.
        """
        await self.check_parent_network(params["parentSigner"])

        # If we have a ParentToChildTransactionRequest, skip building a deposit request
        if is_parent_to_child_transaction_request(params):
            eth_deposit = params
        else:
            eth_deposit = await self.get_deposit_request(
                {**params, "from": params["parentSigner"].account.address}
            )

        tx = {
            **eth_deposit["txRequest"],
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        tx_hash = params["parentSigner"].provider.eth.send_transaction(tx)
        tx_receipt = params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        # monkeyPatchEthDepositWait => extended functionality for final wait or data decode
        return ParentTransactionReceipt.monkey_patch_eth_deposit_wait(tx_receipt)

    async def get_deposit_to_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds a transaction request for depositing ETH (or custom gas token) from the 
        parent chain to a *different* address on the child chain. 
        It uses a retryable ticket flow under the hood.

        :param params: 
          {
             "parentProvider": Web3, 
             "childProvider": Web3, 
             "amount": int,
             "destinationAddress": str,
             ...
          }
        :return: A ParentToChildTransactionRequest with "txRequest" & "retryableData".
        """
        decimals = await get_native_token_decimals({
            "parentProvider": params["parentProvider"],
            "childNetwork": self.child_network,
        })

        # Convert the deposit amount to 18 decimals for the child chain
        amount_to_be_minted_on_child_chain = scale_from_native_token_decimals_to_18_decimals(
            amount=params["amount"],
            decimals=decimals,
        )

        # The parentToChild retryable uses "l2CallValue" to define 
        # how much ETH is minted or credited on L2
        request_params = {
            **params,
            "to": params["destinationAddress"],
            "l2CallValue": amount_to_be_minted_on_child_chain,
            "callValueRefundAddress": params["destinationAddress"],
            "data": "0x",
        }

        # Optional GasOverrides
        gas_overrides = params.get("retryableGasOverrides", {})

        return await ParentToChildMessageCreator.get_ticket_creation_request(
            request_params,
            params["parentProvider"],
            params["childProvider"],
            gas_overrides,
        )

    async def deposit_to(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """
        Executes a deposit from the parent chain to a *different* address on the child chain 
        using a retryable ticket. 
        If a transaction request isn't provided, builds one via get_deposit_to_request().

        :param params: 
          Either an EthDepositToParams object 
          OR a prepared ParentToChildTransactionRequest with "childProvider" + "parentSigner"
        :return: A ParentTransactionReceipt after the deposit is confirmed on the parent chain.
        """
        await self.check_parent_network(params["parentSigner"])
        await self.check_child_network(params["childProvider"])

        # If it's already a ParentToChildTransactionRequest, skip
        if is_parent_to_child_transaction_request(params):
            retryable_ticket_request = params
        else:
            retryable_ticket_request = await self.get_deposit_to_request(
                {
                    **params,
                    "from": params["parentSigner"].account.address,
                    "parentProvider": params["parentSigner"].provider,
                }
            )

        parent_to_child_msg_creator = ParentToChildMessageCreator(params["parentSigner"])
        tx = await parent_to_child_msg_creator.createRetryableTicket(
            retryable_ticket_request,
            params["childProvider"],
        )

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx)

    async def get_withdrawal_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds a transaction request for withdrawing ETH from the Child chain back to the Parent chain.

        :param params: 
          {
            "childSigner" or "childProvider": Web3, 
            "destinationAddress": str,
            "amount": int,
            "from": str,
          }
        :return: A ChildToParentTransactionRequest dict with "txRequest" & "estimateParentGasLimit"
        """
        # The child side uses ArbSys.withdrawEth(...) 
        arb_sys = load_contract(
            provider=params.get("childProvider") or params["childSigner"].provider,
            contract_name="ArbSys",
            address=ARB_SYS_ADDRESS,
            is_classic=False,
        )

        function_data = arb_sys.encodeABI(
            fn_name="withdrawEth",
            args=[params["destinationAddress"]],
        )

        async def estimate_parent_gas_limit(parent_provider) -> int:
            # For L3 scenario or if parent is actually an L2 chain
            if await is_arbitrum_chain(parent_provider):
                return 4_000_000
            # Otherwise standard block on L1
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

    async def withdraw(self, params: Dict[str, Any]) -> ChildTransactionReceipt:
        """
        Withdraws ETH from the child network back to the parent network. 
        If a transaction request isn't already provided, we build one via get_withdrawal_request().

        :param params: A dict that may be either:
          1) EthWithdrawParams + "childSigner"
          2) ChildToParentTxReqAndSigner
        :return: A ChildTransactionReceipt after the withdrawal is executed on the child chain.
        :raises MissingProviderArbSdkError: If no provider is attached to the childSigner.
        """
        if not SignerProviderUtils.signer_has_provider(params["childSigner"]):
            raise MissingProviderArbSdkError("childSigner")

        await self.check_child_network(params["childSigner"])

        # If we already have a ChildToParentTransactionRequest, skip building it
        if is_child_to_parent_transaction_request(params):
            request = params
        else:
            request = await self.get_withdrawal_request(params)

        tx = {
            **request["txRequest"],
            **params.get("overrides", {}),
            "from": params["childSigner"].account.address,
        }
        tx_hash = params["childSigner"].provider.eth.send_transaction(tx)
        tx_receipt = params["childSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ChildTransactionReceipt.monkey_patch_wait(tx_receipt)
