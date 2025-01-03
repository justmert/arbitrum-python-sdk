from collections import namedtuple
from decimal import Decimal

from eth_abi import encode
from eth_typing import HexStr
from web3 import Web3
from web3.exceptions import ContractLogicError

from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.data_entities.constants import DISABLED_GATEWAY
from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from src.lib.data_entities.networks import (
    get_arbitrum_network,
    assert_arbitrum_network_has_token_bridge,
    is_arbitrum_chain,
)
from src.lib.data_entities.retryable_data import RetryableDataTools
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
)
from src.lib.data_entities.transaction_request import (
    is_parent_to_child_transaction_request,
    is_child_to_parent_transaction_request,
)
from src.lib.message.parent_to_child_message_gas_estimator import ParentToChildMessageGasEstimator
from src.lib.message.parent_transaction import ParentTransactionReceipt
from src.lib.message.child_transaction import ChildTransactionReceipt
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import (
    CaseDict,
    is_contract_deployed,
    load_contract,
    get_native_token_decimals,
    scale_from_18_decimals_to_native_token_decimals,
    get_erc20_parent_address_from_parent_to_child_tx_request,
)


class Erc20Bridger(AssetBridger):
    MAX_APPROVAL = 2**256 - 1
    MIN_CUSTOM_DEPOSIT_GAS_LIMIT = 275000

    def __init__(self, child_network):
        super().__init__(child_network)
        assert_arbitrum_network_has_token_bridge(child_network)
        self.child_network = child_network

    @classmethod
    async def from_provider(cls, child_provider):
        child_network = await get_arbitrum_network(child_provider)
        return cls(child_network)

    async def get_parent_gateway_address(self, erc20_parent_address, parent_provider):
        await self.check_parent_network(parent_provider)

        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.child_network.token_bridge.parent_gateway_router,
            is_classic=True,
        )
        return parent_gateway_router.functions.getGateway(erc20_parent_address).call()

    async def get_child_gateway_address(self, erc20_parent_address, child_provider):
        await self.check_child_network(child_provider)
        child_gateway_router = load_contract(
            provider=child_provider,
            contract_name="L2GatewayRouter",
            address=self.child_network.token_bridge.child_gateway_router,
            is_classic=True,
        )
        return child_gateway_router.functions.getGateway(erc20_parent_address).call()

    async def get_approve_gas_token_request(self, params):
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        tx_request = await self.get_approve_token_request(params)
        return {**tx_request, "to": self.native_token}

    async def approve_gas_token(self, params):
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        await self.check_parent_network(params["parentSigner"])

        approve_gas_token_request = (
            await self.get_approve_gas_token_request(
                {
                    **params,
                    "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
                }
            )
            if self.is_approve_params(params)
            else params["txRequest"]
        )

        transaction = {
            **approve_gas_token_request,
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        tx_hash = params["parentSigner"].provider.eth.send_transaction(transaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    async def get_approve_token_request(self, params):
        gateway_address = await self.get_parent_gateway_address(
            params["erc20ParentAddress"],
            SignerProviderUtils.get_provider_or_throw(params["parentProvider"]),
        )

        i_erc20_interface = load_contract(
            provider=params["parentProvider"],
            contract_name="ERC20",
            is_classic=True,
        )

        data = i_erc20_interface.encodeABI(
            fn_name="approve",
            args=[gateway_address, params.get("amount", None) or Erc20Bridger.MAX_APPROVAL],
        )

        return {"to": params["erc20ParentAddress"], "data": data, "value": 0}

    def is_approve_params(self, params):
        return "erc20ParentAddress" in params

    async def approve_token(self, params):
        await self.check_parent_network(params["parentSigner"])
        approve_request = (
            await self.get_approve_token_request(
                {
                    **params,
                    "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
                }
            )
            if self.is_approve_params(params)
            else params["txRequest"]
        )

        transaction = {
            **approve_request,
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        tx_hash = params["parentSigner"].provider.eth.send_transaction(transaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    async def get_withdrawal_events(
        self,
        child_provider,
        gateway_address,
        filter,
        parent_token_address=None,
        from_address=None,
        to_address=None,
    ):
        await self.check_child_network(child_provider)
        event_fetcher = EventFetcher(child_provider)

        argument_filters = {}

        events = await event_fetcher.get_events(
            contract_factory="L2ArbitrumGateway",
            event_name="WithdrawalInitiated",
            argument_filters=argument_filters,
            filter={
                "address": gateway_address,
                **filter,
            },
            is_classic=True,
        )

        events = [{"txHash": a["transactionHash"], **a["event"]} for a in events]
        return (
            [event for event in events if event["l1Token"].lower() == parent_token_address.lower()]
            if parent_token_address
            else events
        )

    async def looks_like_weth_gateway(self, potential_weth_gateway_address, parent_provider):
        try:
            potential_weth_gateway = load_contract(
                provider=parent_provider,
                contract_name="L1WethGateway",
                address=potential_weth_gateway_address,
                is_classic=True,
            )
            potential_weth_gateway.functions.l1Weth().call()
            return True

        except ContractLogicError:
            return False

        except Exception as err:
            raise err

    async def is_weth_gateway(self, gateway_address, parent_provider):
        weth_address = self.child_network.token_bridge.parent_weth_gateway
        if self.child_network.is_custom:
            if await self.looks_like_weth_gateway(gateway_address, parent_provider):
                return True
        elif weth_address == gateway_address:
            return True
        return False

    def get_child_token_contract(self, child_provider, child_token_addr):
        return load_contract(
            provider=child_provider,
            contract_name="L2GatewayToken",
            address=child_token_addr,
            is_classic=True,
        )

    def get_parent_token_contract(self, parent_provider, parent_token_addr):
        return load_contract(
            provider=parent_provider,
            contract_name="ERC20",
            address=parent_token_addr,
            is_classic=True,
        )

    async def get_child_erc20_address(self, erc20_parent_address, parent_provider):
        await self.check_parent_network(parent_provider)
        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.child_network.token_bridge.parent_gateway_router,
            is_classic=True,
        )
        return parent_gateway_router.functions.calculateL2TokenAddress(erc20_parent_address).call()

    async def get_parent_erc20_address(self, erc20_child_chain_address, child_provider):
        await self.check_child_network(child_provider)

        if erc20_child_chain_address.lower() == self.child_network.token_bridge.child_weth.lower():
            return self.child_network.token_bridge.parent_weth

        arb_erc20 = load_contract(
            provider=child_provider,
            contract_name="L2GatewayToken",
            address=erc20_child_chain_address,
            is_classic=True,
        )

        parent_address = arb_erc20.functions.l1Address().call()

        child_gateway_router = load_contract(
            provider=child_provider,
            contract_name="L2GatewayRouter",
            address=self.child_network.token_bridge.child_gateway_router,
            is_classic=True,
        )
        child_address = child_gateway_router.functions.calculateL2TokenAddress(parent_address).call()

        if child_address.lower() != erc20_child_chain_address.lower():
            raise ArbSdkError(
                f"Unexpected parent address. Parent address from token is not registered to the provided child address. {parent_address} {child_address} {erc20_child_chain_address}"
            )
        return parent_address

    async def is_deposit_disabled(self, parent_token_address, parent_provider):
        await self.check_parent_network(parent_provider)
        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.child_network.token_bridge.parent_gateway_router,
            is_classic=True,
        )
        return parent_gateway_router.functions.l1TokenToGateway(parent_token_address).call() == DISABLED_GATEWAY

    def apply_defaults(self, params):
        return {
            **params,
            "excessFeeRefundAddress": params.get("excessFeeRefundAddress", params["from"]),
            "callValueRefundAddress": params.get("callValueRefundAddress", params["from"]),
            "destinationAddress": params.get("destinationAddress", params["from"]),
        }

    def get_deposit_request_call_value(self, deposit_params):
        if not self.native_token_is_eth:
            return 0

        return (
            deposit_params["gasLimit"] * deposit_params["maxFeePerGas"] + deposit_params["maxSubmissionCost"]
        )

    def get_deposit_request_outbound_transfer_inner_data(self, deposit_params, decimals):
        if not self.native_token_is_eth:
            return self._solidity_encode(
                ["uint256", "bytes", "uint256"],
                [
                    int(deposit_params["maxSubmissionCost"]),
                    "0x",
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=deposit_params["gasLimit"] * deposit_params["maxFeePerGas"] 
                        + deposit_params["maxSubmissionCost"],
                        decimals=decimals,
                    ),
                ],
            )

        return self._solidity_encode(
            ["uint256", "bytes"], 
            [int(deposit_params["maxSubmissionCost"]), "0x"]
        )

    async def get_deposit_request(self, params):
        await self.check_parent_network(params["parentProvider"])
        await self.check_child_network(params["childProvider"])

        defaulted_params = self.apply_defaults(params)
        amount = defaulted_params["amount"]
        destination_address = defaulted_params["destinationAddress"]
        erc20_parent_address = defaulted_params["erc20ParentAddress"]
        parent_provider = defaulted_params["parentProvider"]
        child_provider = defaulted_params["childProvider"]
        retryable_gas_overrides = defaulted_params.get("retryableGasOverrides", {})

        parent_gateway_address = await self.get_parent_gateway_address(erc20_parent_address, parent_provider)

        if parent_gateway_address == self.child_network.token_bridge.parent_custom_gateway:
            if "gasLimit" not in retryable_gas_overrides:
                retryable_gas_overrides["gasLimit"] = {}
            if "min" not in retryable_gas_overrides["gasLimit"]:
                retryable_gas_overrides["gasLimit"]["min"] = Erc20Bridger.MIN_CUSTOM_DEPOSIT_GAS_LIMIT

        decimals = await get_native_token_decimals({
            "parentProvider": parent_provider,
            "childNetwork": self.child_network
        })

        def deposit_func(deposit_params):
            deposit_params["maxSubmissionCost"] = params.get(
                "maxSubmissionCost", deposit_params["maxSubmissionCost"]
            )

            inner_data = self.get_deposit_request_outbound_transfer_inner_data(deposit_params, decimals)
            
            i_gateway_router = load_contract(
                provider=parent_provider,
                contract_name="L1GatewayRouter",
                is_classic=True,
            )

            if defaulted_params["excessFeeRefundAddress"] != defaulted_params["from"]:
                function_data = i_gateway_router.encodeABI(
                    fn_name="outboundTransferCustomRefund",
                    args=[
                        erc20_parent_address,
                        defaulted_params["excessFeeRefundAddress"],
                        destination_address,
                        amount,
                        deposit_params["gasLimit"],
                        deposit_params["maxFeePerGas"],
                        inner_data,
                    ],
                )
            else:
                function_data = i_gateway_router.encodeABI(
                    fn_name="outboundTransfer",
                    args=[
                        erc20_parent_address,
                        destination_address,
                        amount,
                        deposit_params["gasLimit"],
                        deposit_params["maxFeePerGas"],
                        inner_data,
                    ],
                )

            return {
                "data": function_data,
                "to": self.child_network.token_bridge.parent_gateway_router,
                "from": defaulted_params["from"],
                "value": self.get_deposit_request_call_value(deposit_params),
            }

        gas_estimator = ParentToChildMessageGasEstimator(child_provider)
        estimates = await gas_estimator.populate_function_params(deposit_func, parent_provider, retryable_gas_overrides)

        async def is_valid():
            re_estimates = await gas_estimator.populate_function_params(
                deposit_func, parent_provider, retryable_gas_overrides
            )
            return ParentToChildMessageGasEstimator.is_valid(estimates["estimates"], re_estimates["estimates"])

        return CaseDict(
            {
                "txRequest": CaseDict(
                    {
                        "to": self.child_network.token_bridge.parent_gateway_router,
                        "data": estimates["data"],
                        "value": estimates["value"],
                        "from": params["from"],
                    }
                ),
                "retryableData": CaseDict({**estimates["retryable"], **estimates["estimates"]}),
                "isValid": is_valid,
            }
        )

    async def deposit(self, params):
        await self.check_parent_network(params["parentSigner"])

        if "overrides" in params and params["overrides"] is not None and "value" in params["overrides"]:
            raise ArbSdkError("Parent call value should be set through l1CallValue param")

        parent_provider = SignerProviderUtils.get_provider_or_throw(params["parentSigner"])

        erc20_parent_address = (
            get_erc20_parent_address_from_parent_to_child_tx_request(params)
            if is_parent_to_child_transaction_request(params)
            else params["erc20ParentAddress"]
        )

        is_registered = await self.is_registered({
            "erc20ParentAddress": erc20_parent_address,
            "parentProvider": parent_provider,
            "childProvider": params["childProvider"]
        })

        if not is_registered:
            parent_chain_id = (await parent_provider.eth.chain_id)
            raise ValueError(
                f"Token {erc20_parent_address} on chain {parent_chain_id} is not registered on the gateways"
            )

        token_deposit = (
            params
            if is_parent_to_child_transaction_request(params)
            else await self.get_deposit_request(
                {
                    **params,
                    "parentProvider": parent_provider,
                    "from": params["parentSigner"].account.address,
                }
            )
        )

        transaction = {
            **token_deposit["txRequest"],
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        tx_hash = params["parentSigner"].provider.eth.send_transaction(transaction)
        tx_receipt = params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)

    async def get_withdrawal_request(self, params):
        to_address = params["destinationAddress"]

        if "childProvider" in params:
            provider = params["childProvider"]
        elif "childSigner" in params:
            provider = params["childSigner"].provider

        router_interface = load_contract(
            provider=provider,
            contract_name="L2GatewayRouter",
            is_classic=True,
        )

        function_data = router_interface.encodeABI(
            fn_name="outboundTransfer",
            args=[
                params["erc20ParentAddress"],
                to_address,
                params["amount"],
                "0x",
            ],
        )

        async def estimate_parent_gas_limit(parent_provider):
            if await is_arbitrum_chain(parent_provider):
                # values for L3 are dependent on the L1 base fee, so hardcoding can never be accurate
                # however, this is only an estimate used for display, so should be good enough
                return 8_000_000

            parent_gateway_address = await self.get_parent_gateway_address(
                params["erc20ParentAddress"], 
                parent_provider
            )
            is_weth = await self.is_weth_gateway(parent_gateway_address, parent_provider)
            return 190000 if is_weth else 160000

        return {
            "txRequest": {
                "data": function_data,
                "to": self.child_network.token_bridge.child_gateway_router,
                "value": 0,
                "from": params["from"],
            },
            "estimateParentGasLimit": estimate_parent_gas_limit,
        }

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params["childSigner"]):
            raise MissingProviderArbSdkError("childSigner")
        await self.check_child_network(params["childSigner"])

        withdrawal_request = (
            params
            if is_child_to_parent_transaction_request(params)
            else await self.get_withdrawal_request({
                **params, 
                "from": params["childSigner"].account.address
            })
        )

        tx = {**withdrawal_request["txRequest"], **params.get("overrides", {})}
        if "from" not in tx:
            tx["from"] = params["childSigner"].account.address

        tx_hash = params["childSigner"].provider.eth.send_transaction(tx)
        tx_receipt = params["childSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ChildTransactionReceipt.monkey_patch_wait(tx_receipt)

    async def is_registered(self, params):
        """
        Checks if the token has been properly registered on both gateways. 
        Mostly useful for tokens that use a custom gateway.
        """
        parent_standard_gateway_address_from_chain_config = (
            self.child_network.token_bridge.parent_erc20_gateway
        )
        
        parent_gateway_address_from_parent_gateway_router = await self.get_parent_gateway_address(
            params["erc20ParentAddress"], 
            params["parentProvider"]
        )

        # token uses standard gateway; no need to check further
        if (
            parent_standard_gateway_address_from_chain_config.lower() ==
            parent_gateway_address_from_parent_gateway_router.lower()
        ):
            return True

        child_token_address_from_parent_gateway_router = await self.get_child_erc20_address(
            params["erc20ParentAddress"],
            params["parentProvider"]
        )

        child_gateway_address_from_child_router = await self.get_child_gateway_address(
            params["erc20ParentAddress"],
            params["childProvider"]
        )

        l2_erc20_gateway = load_contract(
            provider=params["childProvider"],
            contract_name="L2ERC20Gateway",
            address=child_gateway_address_from_child_router,
            is_classic=True,
        )

        child_token_address_from_child_gateway = l2_erc20_gateway.functions.calculateL2TokenAddress(
            params["erc20ParentAddress"]
        ).call()

        return (
            child_token_address_from_parent_gateway_router.lower() ==
            child_token_address_from_child_gateway.lower()
        )

    def _solidity_encode(self, types, values):
        values = [val if val != "0x" else b"" for val in values]
        encoded_values = encode(types, values)
        return encoded_values


class AdminErc20Bridger(Erc20Bridger):
    def percent_increase(self, num: int, increase: int) -> int:
        return num + (num * increase) // 100

    def get_approve_gas_token_for_custom_token_registration_request(self, params):
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        i_erc20_interface = load_contract(
            provider=params["parentProvider"],
            contract_name="ERC20",
            is_classic=True,
        )
        data = i_erc20_interface.encodeABI(
            fn_name="approve",
            args=[params["erc20ParentAddress"], params.get("amount", None) or self.MAX_APPROVAL],
        )

        return {
            "data": data,
            "value": 0,
            "to": self.native_token,
        }

    async def approve_gas_token_for_custom_token_registration(self, params):
        if self.native_token_is_eth:
            raise ValueError("chain uses ETH as its native/gas token")

        await self.check_parent_network(params["parentSigner"])

        approve_gas_token_request = (
            self.get_approve_gas_token_for_custom_token_registration_request({
                **params,
                "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
            })
            if self.is_approve_params(params)
            else params["txRequest"]
        )

        transaction = {
            **approve_gas_token_request,
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        tx_hash = params["parentSigner"].provider.eth.send_transaction(transaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    async def register_custom_token(
        self,
        parent_token_address,
        child_token_address,
        parent_signer,
        child_provider,
    ):
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

        await self.check_parent_network(parent_signer)
        await self.check_child_network(child_provider)

        parent_provider = parent_signer.provider
        parent_sender_address = parent_signer.account.address

        parent_token = load_contract(
            provider=parent_signer.provider,
            contract_name="ICustomToken",
            address=parent_token_address,
            is_classic=True,
        )

        child_token = load_contract(
            provider=child_provider,
            contract_name="IArbToken",
            address=child_token_address,
            is_classic=True,
        )

        if not is_contract_deployed(parent_signer.provider, parent_token.address):
            raise Exception("Parent token is not deployed.")

        if not is_contract_deployed(child_provider, child_token.address):
            raise Exception("Child token is not deployed.")

        if not self.native_token_is_eth:
            native_token_contract = load_contract(
                provider=parent_provider,
                contract_name="ERC20",
                address=self.native_token,
                is_classic=True,
            )
            allowance = native_token_contract.functions.allowance(
                parent_sender_address,
                parent_token.address
            ).call()

            max_fee_per_gas_on_child = child_provider.eth.max_priority_fee
            max_fee_per_gas_on_child_with_buffer = self.percent_increase(max_fee_per_gas_on_child, 500)
            # hardcode gas limit to 60k
            estimated_gas_fee = 60_000 * max_fee_per_gas_on_child_with_buffer

            if allowance < estimated_gas_fee:
                raise ValueError(
                    f"Insufficient allowance. Please increase spending for: owner - {parent_sender_address}, "
                    f"spender - {parent_token.address}."
                )

        parent_address_from_child = child_token.functions.l1Address().call()
        if parent_address_from_child != parent_token_address:
            raise ArbSdkError(
                f"Child token does not have parent address set. Set address: {parent_address_from_child}, "
                f"expected address: {parent_token_address}."
            )

        native_token_decimals = await get_native_token_decimals({
            "parentProvider": parent_provider,
            "childNetwork": self.child_network,
        })

        GasParams = namedtuple("GasParams", ["maxSubmissionCost", "gasLimit"])
        from_address = parent_signer.account.address

        def encode_func_data(set_token_gas, set_gateway_gas, max_fee_per_gas):
            if max_fee_per_gas == RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"]:
                double_fee_per_gas = max_fee_per_gas * 2
            else:
                double_fee_per_gas = max_fee_per_gas

            set_token_deposit = set_token_gas.gasLimit * double_fee_per_gas + set_token_gas.maxSubmissionCost
            set_gateway_deposit = set_gateway_gas.gasLimit * double_fee_per_gas + set_gateway_gas.maxSubmissionCost

            encoded_data = parent_token.encodeABI(
                fn_name="registerTokenOnL2",
                args=[
                    child_token_address,
                    set_token_gas.maxSubmissionCost,
                    set_gateway_gas.maxSubmissionCost,
                    set_token_gas.gasLimit,
                    set_gateway_gas.gasLimit,
                    double_fee_per_gas,
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=set_token_deposit,
                        decimals=native_token_decimals,
                    ),
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=set_gateway_deposit,
                        decimals=native_token_decimals,
                    ),
                    parent_sender_address,
                ],
            )

            return {
                "data": encoded_data,
                "to": parent_token.address,
                "value": set_token_deposit + set_gateway_deposit if self.native_token_is_eth else 0,
                "from": from_address,
            }

        g_estimator = ParentToChildMessageGasEstimator(child_provider)
        set_token_estimates2 = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                GasParams(params["gasLimit"], params["maxSubmissionCost"]),
                GasParams(RetryableDataTools.ErrorTriggeringParams["gasLimit"], 1),
                params["maxFeePerGas"],
            ),
            parent_provider,
        )

        set_gateway_estimates2 = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                GasParams(
                    set_token_estimates2["estimates"]["gasLimit"],
                    set_token_estimates2["estimates"]["maxSubmissionCost"],
                ),
                GasParams(params["gasLimit"], params["maxSubmissionCost"]),
                params["maxFeePerGas"],
            ),
            parent_provider,
        )

        register_tx = {
            "to": parent_token.address,
            "data": set_gateway_estimates2["data"],
            "value": set_gateway_estimates2["value"],
            "from": parent_signer.account.address,
        }

        tx_hash = parent_signer.provider.eth.send_transaction(register_tx)
        register_tx_receipt = parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_wait(register_tx_receipt)

    async def get_parent_gateway_set_events(self, parent_provider, filter):
        await self.check_parent_network(parent_provider)

        parent_gateway_router_address = self.child_network.token_bridge.parent_gateway_router
        event_fetcher = EventFetcher(parent_provider)

        events = await event_fetcher.get_events(
            contract_factory="L1GatewayRouter",
            event_name="GatewaySet",
            argument_filters={},
            filter={
                **filter,
                "address": parent_gateway_router_address,
            },
            is_classic=True,
        )

        return [a["event"] for a in events]

    async def get_child_gateway_set_events(self, child_provider, filter, custom_network_child_gateway_router=None):
        if self.child_network.is_custom and not custom_network_child_gateway_router:
            raise ArbSdkError("Must supply customNetworkChildGatewayRouter for custom network ")

        await self.check_child_network(child_provider)

        child_gateway_router_address = custom_network_child_gateway_router or self.child_network.token_bridge.child_gateway_router
        event_fetcher = EventFetcher(child_provider)

        events = await event_fetcher.get_events(
            contract_factory="L2GatewayRouter",
            event_name="GatewaySet",
            argument_filters={},
            filter={
                **filter,
                "address": child_gateway_router_address,
            },
            is_classic=True,
        )

        return [a["event"] for a in events]

    async def set_gateways(
        self,
        parent_signer,
        child_provider,
        token_gateways,
        options=None,
    ):
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

        await self.check_parent_network(parent_signer)
        await self.check_child_network(child_provider)

        from_address = parent_signer.account.address

        parent_gateway_router = load_contract(
            provider=parent_signer.provider,
            contract_name="L1GatewayRouter",
            address=self.child_network.token_bridge.parent_gateway_router,
            is_classic=True,
        )

        def set_gateways_func(params):
            return {
                "data": parent_gateway_router.encodeABI(
                    fn_name="setGateways",
                    args=[
                        [gateway["tokenAddr"] for gateway in token_gateways],
                        [gateway["gatewayAddr"] for gateway in token_gateways],
                        params["gasLimit"],
                        params["maxFeePerGas"],
                        params["maxSubmissionCost"],
                    ],
                ),
                "to": parent_gateway_router.address,
                "value": params["gasLimit"] * params["maxFeePerGas"] + params["maxSubmissionCost"],
                "from": from_address,
            }

        g_estimator = ParentToChildMessageGasEstimator(child_provider)
        estimates = await g_estimator.populate_function_params(
            set_gateways_func,
            parent_signer.provider,
            options
        )

        transaction = {
            "to": estimates["to"],
            "data": estimates["data"],
            "value": estimates["estimates"]["deposit"],
            "from": parent_signer.account.address,
        }

        tx_hash = parent_signer.provider.eth.send_transaction(transaction)
        tx_receipt = parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)