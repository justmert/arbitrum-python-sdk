from collections import namedtuple

from eth_abi import encode
from web3 import Web3
from web3.exceptions import ContractLogicError

from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.data_entities.constants import DISABLED_GATEWAY
from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.retryable_data import RetryableDataTools
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
)
from src.lib.data_entities.transaction_request import (
    is_l1_to_l2_transaction_request,
    is_l2_to_l1_transaction_request,
)
from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import (
    CaseDict,
    is_contract_deployed,
    load_contract,
)


class Erc20Bridger(AssetBridger):
    MAX_APPROVAL = 2**256 - 1
    MIN_CUSTOM_DEPOSIT_GAS_LIMIT = 275000

    def __init__(self, l2_network):
        super().__init__(l2_network)

    @classmethod
    async def from_provider(cls, l2_provider):
        l2_network = get_l2_network(l2_provider)
        return Erc20Bridger(l2_network)

    async def get_l1_gateway_address(self, erc20_l1_address, l1_provider):
        await self.check_l1_network(l1_provider)

        l1_gateway_router = load_contract(
            provider=l1_provider,
            contract_name="L1GatewayRouter",
            address=self.l2_network.token_bridge.l1_gateway_router,
            is_classic=True,
        )
        return l1_gateway_router.functions.getGateway(erc20_l1_address).call()

    async def get_l2_gateway_address(self, erc20_l1_address, l2_provider):
        await self.check_l2_network(l2_provider)
        l2_gateway_router = load_contract(
            provider=l2_provider,
            contract_name="L2GatewayRouter",
            address=self.l2_network.token_bridge.l2_gateway_router,
            is_classic=True,
        )
        return l2_gateway_router.functions.getGateway(erc20_l1_address).call()

    async def get_approve_token_request(self, params):
        gateway_address = await self.get_l1_gateway_address(
            params["erc20L1Address"],
            SignerProviderUtils.get_provider_or_throw(params["l1Provider"]),
        )
        i_erc20_interface = load_contract(
            provider=params["l1Provider"],
            contract_name="ERC20",
            is_classic=True,
        )

        data = i_erc20_interface.encodeABI(
            fn_name="approve",
            args=[gateway_address, params.get("amount", None) or Erc20Bridger.MAX_APPROVAL],
        )

        return {"to": params["erc20L1Address"], "data": data, "value": 0}

    def is_approve_params(self, params):
        return "erc20L1Address" in params

    async def approve_token(self, params):
        await self.check_l1_network(params["l1Signer"])
        approve_request = (
            await self.get_approve_token_request(
                {
                    **params,
                    "l1Provider": SignerProviderUtils.get_provider_or_throw(params["l1Signer"]),
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
            transaction["from"] = params["l1Signer"].account.address

        tx_hash = params["l1Signer"].provider.eth.send_transaction(transaction)

        tx_receipt = params["l1Signer"].provider.eth.wait_for_transaction_receipt(tx_hash)
        return tx_receipt

    async def get_l2_withdrawal_events(
        self,
        l2_provider,
        gateway_address,
        filter,
        l1_token_address=None,
        from_address=None,
        to_address=None,
    ):
        await self.check_l2_network(l2_provider)
        event_fetcher = EventFetcher(l2_provider)

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
            [event for event in events if event["l1Token"].lower() == l1_token_address.lower()]
            if l1_token_address
            else events
        )

    async def looks_like_weth_gateway(self, potential_weth_gateway_address, l1_provider):
        try:
            potential_weth_gateway = load_contract(
                provider=l1_provider,
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

    async def is_weth_gateway(self, gateway_address, l1_provider):
        weth_address = self.l2_network.token_bridge.l1_weth_gateway
        if self.l2_network.is_custom:
            if await self.looks_like_weth_gateway(gateway_address, l1_provider):
                return True
        elif weth_address == gateway_address:
            return True
        return False

    def get_l2_token_contract(self, l2_provider, l2_token_addr):
        return load_contract(
            provider=l2_provider,
            contract_name="L2GatewayToken",
            address=l2_token_addr,
            is_classic=True,
        )

    def get_l1_token_contract(self, l1_provider, l1_token_addr):
        return load_contract(
            provider=l1_provider,
            contract_name="ERC20",
            address=l1_token_addr,
            is_classic=True,
        )

    async def get_l2_erc20_address(self, erc20_l1_address, l1_provider):
        await self.check_l1_network(l1_provider)
        l1_gateway_router = load_contract(
            provider=l1_provider,
            contract_name="L1GatewayRouter",
            address=self.l2_network.token_bridge.l1_gateway_router,
            is_classic=True,
        )
        return l1_gateway_router.functions.calculateL2TokenAddress(erc20_l1_address).call()

    async def get_l1_erc20_address(self, erc20_l2_address, l2_provider):
        await self.check_l2_network(l2_provider)
        if erc20_l2_address.lower() == self.l2_network.token_bridge.l2_weth.lower():
            return self.l2_network.token_bridge.l1_weth

        arb_erc20 = load_contract(
            provider=l2_provider,
            contract_name="L2GatewayToken",
            address=erc20_l2_address,
            is_classic=True,
        )

        l1_address = arb_erc20.functions.l1Address().call()

        l2_gateway_router = load_contract(
            provider=l2_provider,
            contract_name="L2GatewayRouter",
            address=self.l2_network.token_bridge.l2_gateway_router,
            is_classic=True,
        )
        l2_address = l2_gateway_router.functions.calculateL2TokenAddress(l1_address).call()

        if l2_address.lower() != erc20_l2_address.lower():
            raise ArbSdkError(
                f"Unexpected l1 address. L1 address from token is not registered to the provided l2 address. {l1_address} {l2_address} {erc20_l2_address}"
            )
        return l1_address

    async def l1_token_is_disabled(self, l1_token_address, l1_provider):
        await self.check_l1_network(l1_provider)
        l1_gateway_router = load_contract(
            provider=l1_provider,
            contract_name="L1GatewayRouter",
            address=self.l2_network.token_bridge.l1_gateway_router,
            is_classic=True,
        )
        return (l1_gateway_router.functions.l1TokenToGateway(l1_token_address).call()) == DISABLED_GATEWAY

    def apply_defaults(self, params):
        return {
            **params,
            "excessFeeRefundAddress": params.get("excessFeeRefundAddress", params["from"]),
            "callValueRefundAddress": params.get("callValueRefundAddress", params["from"]),
            "destinationAddress": params.get("destinationAddress", params["from"]),
        }

    async def get_deposit_request(self, params):
        await self.check_l1_network(params["l1Provider"])
        await self.check_l2_network(params["l2Provider"])

        defaulted_params = self.apply_defaults(params)
        amount = defaulted_params["amount"]
        destination_address = defaulted_params["destinationAddress"]
        erc20_l1_address = defaulted_params["erc20L1Address"]
        l1_provider = defaulted_params["l1Provider"]
        l2_provider = defaulted_params["l2Provider"]
        retryable_gas_overrides = defaulted_params.get("retryableGasOverrides", {})

        if retryable_gas_overrides is None:
            retryable_gas_overrides = {}

        l1_gateway_address = await self.get_l1_gateway_address(erc20_l1_address, l1_provider)

        if l1_gateway_address == self.l2_network.tokenBridge.l1CustomGateway:
            if "gasLimit" not in retryable_gas_overrides:
                retryable_gas_overrides["gasLimit"] = {}
            if "min" not in retryable_gas_overrides["gasLimit"]:
                retryable_gas_overrides["gasLimit"]["min"] = Erc20Bridger.MIN_CUSTOM_DEPOSIT_GAS_LIMIT

        def deposit_func(deposit_params):
            inner_data = self._solidity_encode(["uint256", "bytes"], [int(deposit_params["maxSubmissionCost"]), "0x"])
            i_gateway_router = load_contract(
                provider=l1_provider,
                contract_name="L1GatewayRouter",
                address=self.l2_network.token_bridge.l1_gateway_router,
                is_classic=True,
            )

            function_data = i_gateway_router.encodeABI(
                fn_name="outboundTransfer",
                args=[
                    Web3.to_checksum_address(erc20_l1_address),
                    Web3.to_checksum_address(destination_address),
                    int(amount),
                    int(deposit_params["gasLimit"]),
                    int(deposit_params["maxFeePerGas"]),
                    inner_data,
                ],
            )

            return {
                "data": function_data,
                "from": defaulted_params["from"],
                "to": self.l2_network.token_bridge.l1_gateway_router,
                "value": deposit_params["gasLimit"] * deposit_params["maxFeePerGas"]
                + deposit_params["maxSubmissionCost"],
            }

        gas_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await gas_estimator.populate_function_params(deposit_func, l1_provider, retryable_gas_overrides)

        async def is_valid():
            re_estimates = await gas_estimator.populate_function_params(
                deposit_func, l1_provider, retryable_gas_overrides
            )
            return L1ToL2MessageGasEstimator.isValid(estimates["estimates"], re_estimates["estimates"])

        return CaseDict(
            {
                "txRequest": CaseDict(
                    {
                        "to": self.l2_network.tokenBridge.l1GatewayRouter,
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
        await self.check_l1_network(params["l1Signer"])

        if "overrides" in params and params["overrides"] is not None and "value" in params["overrides"]:
            raise ArbSdkError("L1 call value should be set through l1CallValue param")

        l1_provider = SignerProviderUtils.get_provider_or_throw(params["l1Signer"])

        if is_l1_to_l2_transaction_request(params):
            token_deposit = params
        else:
            token_deposit = await self.get_deposit_request(
                {
                    **params,
                    "l1Provider": l1_provider,
                    "from": params["l1Signer"].account.address,
                }
            )

        transaction = {
            **token_deposit["txRequest"],
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["l1Signer"].account.address

        tx_hash = params["l1Signer"].provider.eth.send_transaction(transaction)

        tx_receipt = params["l1Signer"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)

    async def get_withdrawal_request(self, params):
        to_address = params["destinationAddress"]

        if "l2Provider" in params:
            provider = params["l2Provider"]

        elif "l2Signer" in params:
            provider = params["l2Signer"].provider

        router_interface = load_contract(
            provider=provider,
            contract_name="L2GatewayRouter",
            is_classic=True,
        )

        function_data = router_interface.encodeABI(
            fn_name="outboundTransfer",
            args=[
                params["erc20L1Address"],
                to_address,
                params["amount"],
                "0x",
            ],
        )

        async def estimate_l1_gas_limit(l1_provider):
            l1_gateway_address = await self.get_l1_gateway_address(params["erc20L1Address"], l1_provider)

            is_weth = await self.is_weth_gateway(l1_gateway_address, l1_provider)

            gas_estimate = 180000 if is_weth else 160000

            return gas_estimate

        return {
            "txRequest": {
                "data": function_data,
                "to": self.l2_network.token_bridge.l2_gateway_router,
                "value": 0,
                "from": params["from"],
            },
            "estimateL1GasLimit": estimate_l1_gas_limit,
        }

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params["l2Signer"]):
            raise MissingProviderArbSdkError("l2Signer")
        await self.check_l2_network(params["l2Signer"])

        withdrawal_request = (
            params
            if is_l2_to_l1_transaction_request(params)
            else await self.get_withdrawal_request({**params, "from": params["l2Signer"].account.address})
        )
        tx = {**withdrawal_request["txRequest"], **params.get("overrides", {})}

        if "from" not in tx:
            tx["from"] = params["l2Signer"].account.address

        tx_hash = params["l2Signer"].provider.eth.send_transaction(tx)

        tx_receipt = params["l2Signer"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return L2TransactionReceipt.monkey_patch_wait(tx_receipt)

    def _solidity_encode(self, types, values):
        values = [val if val != "0x" else b"" for val in values]

        encoded_values = encode(types, values)
        return encoded_values


class AdminErc20Bridger(Erc20Bridger):
    async def register_custom_token(
        self,
        l1_token_address,
        l2_token_address,
        l1_signer,
        l2_provider,
    ):
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError("l1Signer")

        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        l1_sender_address = l1_signer.account.address

        l1_token = load_contract(
            provider=l1_signer.provider,
            contract_name="ICustomToken",
            address=l1_token_address,
            is_classic=True,
        )

        l2_token = load_contract(
            provider=l2_provider,
            contract_name="IArbToken",
            address=l2_token_address,
            is_classic=True,
        )

        if not is_contract_deployed(l1_signer.provider, l1_token.address):
            raise Exception("L1 token is not deployed.")

        if not is_contract_deployed(l2_provider, l2_token.address):
            raise Exception("L2 token is not deployed.")

        l1_address_from_l2 = l2_token.functions.l1Address().call()
        if l1_address_from_l2 != l1_token_address:
            raise ArbSdkError(
                f"L2 token does not have l1 address set. Set address: {l1_address_from_l2}, expected address: {l1_token_address}."
            )

        from_address = l1_signer.account.address

        GasParams = namedtuple("GasParams", ["maxSubmissionCost", "gasLimit"])

        def encode_func_data(set_token_gas, set_gateway_gas, max_fee_per_gas):
            if max_fee_per_gas == RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"]:
                double_fee_per_gas = max_fee_per_gas * 2
            else:
                double_fee_per_gas = max_fee_per_gas

            set_token_deposit = set_token_gas.gasLimit * double_fee_per_gas + set_token_gas.maxSubmissionCost
            set_gateway_deposit = set_gateway_gas.gasLimit * double_fee_per_gas + set_gateway_gas.maxSubmissionCost

            encoded_data = l1_token.encodeABI(
                fn_name="registerTokenOnL2",
                args=[
                    l2_token_address,
                    set_token_gas.maxSubmissionCost,
                    set_gateway_gas.maxSubmissionCost,
                    set_token_gas.gasLimit,
                    set_gateway_gas.gasLimit,
                    double_fee_per_gas,
                    set_token_deposit,
                    set_gateway_deposit,
                    l1_sender_address,
                ],
            )

            return {
                "data": encoded_data,
                "to": l1_token.address,
                "value": set_token_deposit + set_gateway_deposit,
                "from": from_address,
            }

        l1_provider = l1_signer.provider
        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        set_token_estimates2 = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                GasParams(params["gasLimit"], params["maxSubmissionCost"]),
                GasParams(RetryableDataTools.ErrorTriggeringParams["gasLimit"], 1),
                params["maxFeePerGas"],
            ),
            l1_provider,
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
            l1_provider,
        )

        register_tx = {
            "to": l1_token.address,
            "data": set_gateway_estimates2["data"],
            "value": set_gateway_estimates2["value"],
        }

        if "from" not in register_tx:
            register_tx["from"] = l1_signer.account.address

        tx_hash = l1_signer.provider.eth.send_transaction(register_tx)

        register_tx_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return L1TransactionReceipt.monkey_patch_contract_call_wait(register_tx_receipt)

    async def get_l1_gateway_set_events(self, l1_provider, filter, custom_network_l1_gateway_router=None):
        await self.check_l1_network(l1_provider)

        l1_gateway_router_address = self.l2_network.token_bridge.l1_gateway_router

        event_fetcher = EventFetcher(l1_provider)

        argument_filters = {}

        events = await event_fetcher.get_events(
            contract_factory="L1GatewayRouter",
            event_name="GatewaySet",
            argument_filters=argument_filters,
            filter={
                "fromBlock": filter["fromBlock"],
                "toBlock": filter["toBlock"],
                "address": l1_gateway_router_address,
                **filter,
            },
            is_classic=True,
        )

        return [a["event"] for a in events]

    async def get_l2_gateway_set_events(self, l2_provider, filter, custom_network_l2_gateway_router=None):
        if self.l2_network.is_custom and not custom_network_l2_gateway_router:
            raise ArbSdkError("Must supply customNetworkL2GatewayRouter for custom network ")

        await self.check_l2_network(l2_provider)

        l2_gateway_router_address = custom_network_l2_gateway_router or self.l2_network.token_bridge.l2_gateway_router
        event_fetcher = EventFetcher(l2_provider)

        argument_filters = {}

        events = await event_fetcher.get_events(
            contract_factory="L2GatewayRouter",
            event_name="GatewaySet",
            argument_filters=argument_filters,
            filter={
                "fromBlock": filter["fromBlock"],
                "toBlock": filter["toBlock"],
                "address": l2_gateway_router_address,
                **filter,
            },
            is_classic=True,
        )

        return [a["event"] for a in events]

    async def set_gateways(
        self,
        l1_signer,
        l2_provider,
        token_gateways,
        options=None,
    ):
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError("l1Signer")

        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        from_address = l1_signer.account.address

        l1_gateway_router = load_contract(
            provider=l1_signer.provider,
            contract_name="L1GatewayRouter",
            address=self.l2_network.token_bridge.l1_gateway_router,
            is_classic=True,
        )

        def set_gateways_func(params):
            return {
                "data": l1_gateway_router.encodeABI(
                    fn_name="setGateways",
                    args=[
                        [gateway["tokenAddr"] for gateway in token_gateways],
                        [gateway["gatewayAddr"] for gateway in token_gateways],
                        params["gasLimit"],
                        params["maxFeePerGas"],
                        params["maxSubmissionCost"],
                    ],
                ),
                "to": l1_gateway_router.address,
                "value": params["gasLimit"] * params["maxFeePerGas"] + params["maxSubmissionCost"],
                "from": from_address,
            }

        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await g_estimator.populate_function_params(set_gateways_func, l1_signer.provider, options)
        transaction = {
            "to": estimates["to"],
            "data": estimates["data"],
            "value": estimates["estimates"]["deposit"],
        }

        if "from" not in transaction:
            transaction["from"] = l1_signer.account.address

        tx_hash = l1_signer.provider.eth.send_transaction(transaction)

        tx_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)
