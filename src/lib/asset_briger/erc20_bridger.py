from pkg_resources import get_provider
from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from src.lib.data_entities.constants import DISABLED_GATEWAY
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.retryable_data import RetryableDataTools
from web3.providers import BaseProvider
from web3.contract import Contract
from web3 import Web3
from src.lib.utils.helper import (
    CaseDict,
    deploy_abi_contract,
    is_contract_deployed,
    load_contract,
    sign_and_sent_raw_transaction,
)
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.data_entities.transaction_request import (
    is_l1_to_l2_transaction_request,
    is_l2_to_l1_transaction_request,
)
from src.lib.data_entities.networks import L1Network, L2Network, EthBridge, TokenBridge
from eth_abi import encode
from web3 import Web3
from collections import namedtuple

MAX_APPROVAL = 2**256 - 1
MIN_CUSTOM_DEPOSIT_GAS_LIMIT = 275000
MAX_UINT256 = 2**256 - 1


class Erc20Bridger(AssetBridger):
    def __init__(self, l2_network):
        super().__init__(l2_network)

    @classmethod
    async def from_provider(cls, l2_provider):
        l2_network = await get_l2_network(l2_provider)
        return cls(l2_network)

    async def get_l1_gateway_address(self, erc20_l1_address, l1_provider):
        await self.check_l1_network(l1_provider)
        print("gatway_erc20", erc20_l1_address)
        print("l1_gateway_router", self.l2_network.token_bridge.l1_gateway_router)
        # l1 gateway router 0x1D55838a9EC169488D360783D65e6CD985007b72

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
        # print("aaa", SignerProviderUtils.get_provider_or_throw(params["l1Provider"]))
        gateway_address = await self.get_l1_gateway_address(
            params["erc20L1Address"],
            SignerProviderUtils.get_provider_or_throw(params["l1Provider"]),
        )
        i_erc20_interface = load_contract(
            provider=params["l1Provider"],
            contract_name="ERC20",
            address=params["erc20L1Address"],
            is_classic=True,
        )

        # Encode the function call
        data = i_erc20_interface.functions.approve(
            gateway_address, params.get("amount", MAX_APPROVAL)
        ).build_transaction(
            {
                # 'from': w3.eth.default_account  # This needs to be the account that will send the transaction
            }
        )["data"]

        # data = i_erc20_interface.encodeABI(
        #     fn_name="approve",
        #     args=[
        #         gateway_address, 
        #         params.get("amount", MAX_APPROVAL)
        #     ],
        # )


        return {"to": params["erc20L1Address"], "data": data, "value": 0}

    async def approve_token(self, params):
        await self.check_l1_network(params["l1Signer"])
        approve_request = (
            await self.get_approve_token_request({
                **params,
                "l1Provider": SignerProviderUtils.get_provider_or_throw(params['l1Signer']),
            })
            if SignerProviderUtils.get_provider_or_throw(params["l1Signer"])
            else params["txRequest"]
        )

        # l1_provider = SignerProviderUtils.get_provider_or_throw(params["l1Signer"])
        # Merge any overrides
        transaction = {
            **approve_request,
            **params.get("overrides", {"gasPrice": Web3.to_wei("21", "gwei")}),
        }

        tx_receipt = sign_and_sent_raw_transaction(
            signer=params["l1Signer"], tx = transaction
        )
        # # Estimate gas and set the transaction parameters
        # transaction["gas"] = l1_provider.eth.estimate_gas(transaction)
        # transaction["nonce"] = l1_provider.eth.get_transaction_count(
        #     params["l1Signer"].account.address
        # )
        # transaction["chainId"] = l1_provider.eth.chain_id

        # # Sign the transaction
        # signed_txn = params["l1Signer"].account.sign_transaction(transaction)

        # # Send the transaction
        # tx_hash = l1_provider.eth.send_raw_transaction(
        #     signed_txn.rawTransaction
        # )

        # # Wait for the transaction to be mined
        # tx_receipt = l1_provider.eth.wait_for_transaction_receipt(tx_hash)

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
        l2_arbitrum_gateway = load_contract(
            provider=l2_provider,
            contract_name="L2ArbitrumGateway",
            address=gateway_address,
            is_classic=True,
        )
        events = await event_fetcher.get_events(
            l2_arbitrum_gateway.abi,
            lambda contract: contract.filters.WithdrawalInitiated(
                None, from_address, to_address
            ),
            {**filter, "address": gateway_address},
        )
        return (
            [
                event
                for event in events
                if event.l1Token.lower() == l1_token_address.lower()
            ]
            if l1_token_address
            else events
        )

    async def looks_like_weth_gateway(
        self, potential_weth_gateway_address, l1_provider
    ):
        try:
            potential_weth_gateway = load_contract(
                provider=l1_provider,
                contract_name="L1WethGateway",
                address=potential_weth_gateway_address,
                is_classic=True,
            )
            # potential_weth_gateway = L1WethGateway(potential_weth_gateway_address, l1_provider)
            potential_weth_gateway.functions.l1Weth().call()
            return True
        except Exception as err:
            if isinstance(
                err, Web3.exceptions.ContractLogicError
            ) and "CALL_EXCEPTION" in str(err):
                return False
            else:
                raise err

    async def is_weth_gateway(self, gateway_address, l1_provider):
        weth_address = self.l2_network.token_bridge.l1_weth_gateway
        if self.l2_network.is_custom:
            if await self.looks_like_weth_gateway(gateway_address, l1_provider):
                return True
        elif weth_address == gateway_address:
            return True
        return False

    def get_l2_token_contract(self, l2_provider, l2_token_addr) -> Contract:
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
        # l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return l1_gateway_router.functions.calculateL2TokenAddress(
            erc20_l1_address
        ).call()

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
        # l2_gateway_router = L2GatewayRouter(self.l2_network.token_bridge.l2_gateway_router, l2_provider)
        l2_address = l2_gateway_router.functions.calculateL2TokenAddress(
            l1_address
        ).call()

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
        # l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return (
            l1_gateway_router.functions.l1TokenToGateway(l1_token_address).call()
        ) == DISABLED_GATEWAY

    def apply_defaults(self, params):
        return {
            **params,
            "excessFeeRefundAddress": params.get(
                "excessFeeRefundAddress", params["from"]
            ),
            "callValueRefundAddress": params.get(
                "callValueRefundAddress", params["from"]
            ),
            "destinationAddress": params.get("destinationAddress", params["from"]),
        }

    async def get_withdrawal_request(self, params):
        to_address = params["destination_address"]
        router_interface = load_contract(
            provider=params["l2Provider"],
            contract_name="L2GatewayRouter",
            address=self.l2_network.token_bridge.l2_gateway_router,
            is_classic=True,
        )
        # router_interface = L2GatewayRouter.create_interface()  # Make sure to implement create_interface
        function_data = router_interface.encodeFunctionData(
            "outboundTransfer(address,address,uint256,bytes)",
            [
                params["erc20l1_address"],
                to_address,
                int(params["amount"]),
                "0x",
            ],
        )

        l1_gateway_address = await self.get_l1_gateway_address(
            params["erc20l1_address"], params["l1_provider"]
        )
        is_weth = await self.is_weth_gateway(l1_gateway_address, params["l1_provider"])
        gas_estimate = Web3.toInt(180000) if is_weth else Web3.toInt(160000)

        return {
            "txRequest": {
                "data": function_data,
                "to": self.l2_network.token_bridge.l2_gateway_router,
                "value": Web3.toInt(0),
                "from": params["from"],
            },
            "estimate_l1_gas_limit": gas_estimate,  # This is a placeholder, replace with actual estimation logic.
        }

    async def _estimate_l1_gas_limit(self, l1_provider, params):
        l1_gateway_address = await self.get_l1_gateway_address(
            params["erc20l1Address"], l1_provider
        )
        is_weth = await self.is_weth_gateway(l1_gateway_address, l1_provider)
        return 180000 if is_weth else 160000

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params["l2Signer"]):
            raise MissingProviderArbSdkError("l2Signer")
        await self.check_l2_network(params["l2Signer"])

        withdrawal_request = (
            params
            if SignerProviderUtils.signer_has_provider(params["l2Signer"])
            else await self.get_withdrawal_request(
                {**params, "from": params["l2Signer"].account.address}
            )
        )

        tx = await params["l2Signer"].provider.send_transaction(
            {**withdrawal_request["txRequest"], **params.get("overrides", {})}
        )

        
        return L2TransactionReceipt.monkey_patch_wait(tx)

    async def deposit(self, params):
        print('hi0')
        if not SignerProviderUtils.signer_has_provider(params["l1Signer"]):
            raise MissingProviderArbSdkError("l1Signer")

        await self.check_l1_network(params["l1Signer"])
        print('hi1')
        l1_provider = SignerProviderUtils.get_provider_or_throw(params["l1Signer"])

        print("deposit_params", params)
        # Determine if the request is an L1 to L2 transaction request
        if is_l1_to_l2_transaction_request(params):
            token_deposit = params
        else:
            # Prepare the deposit request
            token_deposit = await self.get_deposit_request({
                **params,
                "l1Provider": l1_provider,
                "from": params["l1Signer"].account.address,
            })
        print('hi2')

        # convert from and to addresses to checksum addresses
        # Combine with overrides
        transaction = {
            **token_deposit["txRequest"],
            **params.get("overrides", {"gasPrice": Web3.to_wei("21", "gwei")}),
        }

        # if isinstance(transaction['from'], Contract):
        #     transaction['from'] = transaction['from'].address

        # elif isinstance(transaction['from'], str):
        #     transaction['from'] = Web3.to_checksum_address(transaction['from'])

        # if isinstance(transaction['to'], Contract):
        #     transaction['to'] = transaction['to'].address

        # elif isinstance(transaction['to'], str):
        #     transaction['to'] = Web3.to_checksum_address(transaction['to'])
        tx_receipt = sign_and_sent_raw_transaction(
            signer = params["l1Signer"], tx = transaction
        )
        # print('hi3')

        # transaction["value"] = (
        #     int(transaction["value"]) if "value" in transaction else 0
        # )
        # # Estimate gas and set the transaction parameters
        # print("HEREISMYTRANSACTIONNNN", transaction)
        # transaction["gas"] = l1_provider.eth.estimate_gas(transaction)
        # transaction["nonce"] = l1_provider.eth.get_transaction_count(
        #     params["l1Signer"].account.address
        # )
        # transaction["chainId"] = l1_provider.eth.chain_id

        # # Sign the transaction with the private key
        # signed_txn = params["l1Signer"].account.sign_transaction(transaction)

        # # Send the transaction
        # tx_hash = params["l1Signer"].provider.eth.send_raw_transaction(
        #     signed_txn.rawTransaction
        # )
        # print('hi4')

        # print("---------------------TX_HASH", tx_hash)
        # print("---------------------TX_HASH_HASH", Web3.to_hex(tx_hash))
        # # # Wait for the transaction to be mined and get the receipt
        # tx_receipt = params["l1Signer"].provider.eth.wait_for_transaction_receipt(
        #     tx_hash
        # )
        # print("---------------------TX_RECEIPT", tx_receipt)
    
        # TO-DO
        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)

    def solidity_encode(self, types, values):
        # Correctly handle '0x' string to be an empty byte string
        values = [val if val != "0x" else b"" for val in values]

        # ABI encode the values
        encoded_values = encode(types, values)
        return encoded_values

    async def get_deposit_request(self, params):
        # Check networks
        
        # Implement checkL1Network and checkL2Network
        await self.check_l1_network(params["l1Provider"])
        await self.check_l2_network(params["l2Provider"])

        # Apply defaults to the parameters
        # Implement apply_defaults
        defaulted_params = CaseDict(self.apply_defaults(params))
        # print('def_aparams', defaulted_params)

        # Extract necessary parameters
        amount = defaulted_params["amount"]
        destination_address = defaulted_params["destination_address"]
        erc20_l1_address = defaulted_params["erc20_l1_address"]
        l1_provider = defaulted_params["l1Provider"]
        l2_provider = defaulted_params["l2Provider"]
        retryable_gas_overrides = defaulted_params.get("retryable_gas_overrides", {})

        if retryable_gas_overrides is None:
            retryable_gas_overrides = {}
        print("retryable_gas_overrides", retryable_gas_overrides)
        # Get L1 gateway address
        l1_gateway_address = await self.get_l1_gateway_address(
            erc20_l1_address, l1_provider
        )

        # Adjust for custom gateway deposits
        if l1_gateway_address == self.l2_network.tokenBridge.l1CustomGateway:
            if "gasLimit" not in retryable_gas_overrides:
                retryable_gas_overrides["gasLimit"] = {}
            if "min" not in retryable_gas_overrides["gasLimit"]:
                retryable_gas_overrides["gasLimit"][
                    "min"
                ] = MIN_CUSTOM_DEPOSIT_GAS_LIMIT

        print("updated_retryable_gas_overrides", retryable_gas_overrides)

        # Define deposit function
        def deposit_func(deposit_params):
            print(deposit_params["maxSubmissionCost"])
            inner_data = self.solidity_encode(
                ["uint256", "bytes"], [int(deposit_params["maxSubmissionCost"]), "0x"]
            )
            # i_gateway_router = load_contract(contract_name='L1GatewayRouter')
            i_gateway_router = load_contract(
                provider=l1_provider,
                contract_name="L1GatewayRouter",
                address=self.l2_network.token_bridge.l1_gateway_router,
                is_classic=True,
            )
            # Get the contract function
            # Create encoded data for the function call

            print("------start-")
            print("gaslimit", deposit_params["gasLimit"])
            print("maxfeepergas", deposit_params["maxFeePerGas"])
            print("------end-")
            encoded_data = i_gateway_router.functions.outboundTransfer(
                Web3.to_checksum_address(erc20_l1_address),
                Web3.to_checksum_address(destination_address),
                int(amount),
                int(deposit_params["gasLimit"]),
                int(deposit_params["maxFeePerGas"]),
                inner_data,
            ).build_transaction(
                {
                    "from": defaulted_params["from"],
                    "gas": 222780,  # Explicitly set gas to avoid automatic estimation
                    "gasPrice": Web3.to_wei("21", "gwei"),
                    "value": deposit_params["gasLimit"] * deposit_params["maxFeePerGas"]
                    + deposit_params["maxSubmissionCost"],
                }
            )
            return encoded_data

        # Estimate gas
        gas_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await gas_estimator.populate_function_params(
            deposit_func, l1_provider, retryable_gas_overrides
        )
        print("estimates", estimates)
        print("o1o1o1o1o1o1oo1o1o1o1oo1o1o")
        return CaseDict({
            "txRequest": CaseDict({
                "to": self.l2_network.tokenBridge.l1GatewayRouter,
                "data": estimates["data"],
                "value": estimates["value"],
                "from": params["from"],
            }),
            "retryableData": CaseDict({**estimates["retryable"], **estimates["estimates"]}),
            "isValid": lambda: L1ToL2MessageGasEstimator.is_valid(
                estimates["estimates"], re_estimates["estimates"]
            ),
        })


class AdminErc20Bridger(Erc20Bridger):
    async def register_custom_token(
        self,
        l1_token_address,
        l2_token_address,
        l1_signer: SignerOrProvider,
        l2_provider,
    ) -> Contract:
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError("l1Signer")
        
        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        l1_sender_address = l1_signer.account.address

        # print("admin_erc20_bridger")
        # l1_token = load_contract(provider=l1_signer.provider, contract_name='ICustomToken', address=l1_token_address, is_classic=True)
        # l2_token = load_contract(provider=l2_provider, contract_name='IArbToken', address=l2_token_address, is_classic=True)

        # l1_token_addr = deploy_abi_contract(provider=l1_signer.provider, contract_name="ICustomToken", is_classic=True, deployer=l1_signer.account, constructor_args=[])

        # l2_token_addr = deploy_abi_contract(provider=l2_provider, contract_name="IArbToken", is_classic=True, deployer=l2_signer.account, constructor_args=[])

        # from web3.exceptions import BadFunctionCallOutput

        # def is_contract_deployed(provider: Web3, contract_address: str) -> bool:
        #     print('coddeee', provider.eth.get_code(contract_address))
        #     return provider.eth.get_code(contract_address) != '0x'

        l1_token = load_contract(
            provider=l1_signer.provider,
            contract_name="ICustomToken",
            address=l1_token_address,
            is_classic=True,
        )

        # l1_token_addr = deploy_abi_contract(
        #     provider=l1_signer.provider, deployer = l1_signer.account, contract_name = 'ICustomToken', is_classic=True, constructor_args=[]
        # )
        l2_token = load_contract(
            provider=l2_provider,
            contract_name="IArbToken",
            address=l2_token_address,
            is_classic=True,
        )

        # Sanity checks
        # if not is_contract_deployed(l1_signer.provider, l1_token.address):
        #     raise Exception('L1 token is not deployed.')

        # if not is_contract_deployed(l2_provider, l2_token.address):
        #     raise Exception('L2 token is not deployed.')

        # Call the contract function
        # try:
        #     l1_address_from_l2 = l2_token.functions.l1Address().call()
        #     raise Exception("Failed to call l1Address on L2 token. The contract may not be deployed correctly.")

        # # Sanity checks
        # if not is_contract_deployed(l1_signer.provider, l1_token.address):
        #     raise ArbSdkError('L1 token is not deployed.')

        # # if not l2_token.is_deployed():
        # if not is_contract_deployed(l2_provider, l2_token.address):
        #     raise ArbSdkError('L2 token is not deployed.')

        l1_address_from_l2 = l2_token.functions.l1Address().call()
        if l1_address_from_l2 != l1_token_address:
            raise ArbSdkError(
                f"L2 token does not have l1 address set. Set address: {l1_address_from_l2}, expected address: {l1_token_address}."
            )

        print("admin_erc20_bridger1")

        from_address = l1_signer.account.address

        # # Define gas parameter types
        GasParams = namedtuple("GasParams", ["maxSubmissionCost", "gasLimit"])

        def encode_func_data(set_token_gas, set_gateway_gas, max_fee_per_gas: int):
            # Calculate deposit values for token and gateway registration
            # The above code is calculating the value of `double_fee_per_gas` by multiplying the value

            if (
                max_fee_per_gas
                == RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"]
            ):
                double_fee_per_gas = max_fee_per_gas * 2
            else:
                double_fee_per_gas = max_fee_per_gas

            set_token_deposit = (
                set_token_gas.gasLimit * double_fee_per_gas
                + set_token_gas.maxSubmissionCost
            )
            set_gateway_deposit = (
                set_gateway_gas.gasLimit * double_fee_per_gas
                + set_gateway_gas.maxSubmissionCost
            )

            print("l2_token_address", l2_token_address)
            print("l1_token_address", l1_token_address)
            print("set_token_gas.maxSubmissionCost", set_token_gas.maxSubmissionCost)
            print(
                "set_gateway_gas.maxSubmissionCost", set_gateway_gas.maxSubmissionCost
            )
            print("set_token_gas.gasLimit", set_token_gas.gasLimit)
            print("set_gateway_gas.gasLimit", set_gateway_gas.gasLimit)
            print("double_fee_per_gas", double_fee_per_gas)
            print("set_token_deposit", set_token_deposit)
            print("set_gateway_deposit", set_gateway_deposit)
            print("l1_sender_address", l1_sender_address)
            print("l1_tokenaddr", l1_token.address)
            encoded_data = l1_token.functions.registerTokenOnL2(
                l2_token_address,
                set_token_gas.maxSubmissionCost,
                set_gateway_gas.maxSubmissionCost,
                set_token_gas.gasLimit,
                set_gateway_gas.gasLimit,
                double_fee_per_gas,
                set_token_deposit,
                set_gateway_deposit,
                l1_sender_address,
            ).build_transaction(
                {
                    "from": from_address,
                    "gas": 22780,
                    "gasPrice": Web3.to_wei("21", "gwei"),
                    "value": set_token_deposit + set_gateway_deposit,
                }
            )

            return {
                "data": encoded_data["data"],
                "to": l1_token.address,
                "value": set_token_deposit + set_gateway_deposit,
                "from": from_address,
            }

        # Estimate gas for setting token and gateway parameters
        # Assuming L1ToL2MessageGasEstimator and RetryableDataTools are implemented
        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        set_token_estimates = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                GasParams(params["gasLimit"], params["maxSubmissionCost"]),
                GasParams(RetryableDataTools.ErrorTriggeringParams["gasLimit"], 1),
                params["maxFeePerGas"],
            ),
            l1_signer.provider,
        )

        set_gateway_estimates = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                GasParams(
                    set_token_estimates["estimates"]["gasLimit"],
                    set_token_estimates["estimates"]["maxSubmissionCost"],
                ),
                GasParams(params["gasLimit"], params["maxSubmissionCost"]),
                params["maxFeePerGas"],
            ),
            l1_signer.provider,
        )

        print('gas estimate', set_gateway_estimates["estimates"]["gasLimit"])
        transaction = {
            "to": l1_token.address,
            "data": set_gateway_estimates["data"],
            "value": set_gateway_estimates["value"],
            "from": l1_signer.account.address,
        } 
        register_tx_receipt = sign_and_sent_raw_transaction(l1_signer, transaction)
        
        return L1TransactionReceipt.monkey_patch_contract_call_wait(register_tx_receipt)

    async def get_l1_gateway_set_events(
        self, l1_provider, filter, custom_network_l1_gateway_router=None
    ) -> list:
        # if self.l2_network.is_custom and not custom_network_l2_gateway_router:
        #     raise ArbSdkError('Must supply customNetworkL2GatewayRouter for custom network ')
        await self.check_l1_network(l1_provider)

        l1_gateway_router_address = (
            custom_network_l1_gateway_router
            or self.l2_network.token_bridge.l1_gateway_router
        )
        event_fetcher = EventFetcher(l1_provider)
        L1GatewayRouter = load_contract(
            provider=l1_provider,
            contract_name="L1GatewayRouter",
            address=l1_gateway_router_address,
            is_classic=True,
        )
        events = await event_fetcher.get_events(
            L1GatewayRouter,
            lambda t: t.filters.GatewaySet(),
            {**filter, "address": l1_gateway_router_address},
        )
        return [a["event"] for a in events]

    async def get_l2_gateway_set_events(
        self, l2_provider, filter, custom_network_l2_gateway_router=None
    ) -> list:
        # if self.l2_network.is_custom and not custom_network_l2_gateway_router:
        #     raise ArbSdkError('Must supply customNetworkL2GatewayRouter for custom network ')
        await self.check_l2_network(l2_provider)

        l2_gateway_router_address = (
            custom_network_l2_gateway_router
            or self.l2_network.token_bridge.l2_gateway_router
        )
        event_fetcher = EventFetcher(l2_provider)
        L2GatewayRouter = load_contract(
            provider=l2_provider,
            contract_name="L2GatewayRouter",
            address=l2_gateway_router_address,
            is_classic=True,
        )
        events = await event_fetcher.get_events(
            L2GatewayRouter,
            lambda t: t.filters.GatewaySet(),
            {**filter, "address": l2_gateway_router_address},
        )
        return [a["event"] for a in events]

    def _encode_set_gateways_data(
        self, token_gateways, params, l1_gateway_router, from_address
    ):
        # Construct the transaction data for setting gateways
        token_addresses = [gateway["tokenAddr"] for gateway in token_gateways]
        gateway_addresses = [gateway["gatewayAddr"] for gateway in token_gateways]

        # Ensure token_addresses and gateway_addresses are lists of string addresses
        if all(isinstance(token_address, str) for token_address in token_addresses):
            token_addresses = [
                Web3.to_checksum_address(token_address)
                for token_address in token_addresses
            ]

        elif all(
            isinstance(token_address, Contract) for token_address in token_addresses
        ):
            token_addresses = [
                Web3.to_checksum_address(gateway["tokenAddr"].address)
                for gateway in token_gateways
            ]

        else:
            raise ArbSdkError(
                "token_addresses must be lists of string addresses or Contract instances."
            )

        if all(
            isinstance(gateway_address, str) for gateway_address in gateway_addresses
        ):
            gateway_addresses = [
                Web3.to_checksum_address(gateway_address)
                for gateway_address in gateway_addresses
            ]

        elif all(
            isinstance(gateway_address, Contract)
            for gateway_address in gateway_addresses
        ):
            gateway_addresses = [
                Web3.to_checksum_address(gateway["gatewayAddr"].address)
                for gateway in token_gateways
            ]

        else:
            raise ArbSdkError(
                "gateway_addresses must be lists of string addresses or Contract instances."
            )

        # Convert integer values to Web3 BigNumber format
        gas_limit = int(params["gasLimit"])
        max_fee_per_gas = int(params["maxFeePerGas"])
        max_submission_cost = int(params["maxSubmissionCost"])

        transaction_data = l1_gateway_router.functions.setGateways(
            token_addresses,
            gateway_addresses,
            gas_limit,
            max_fee_per_gas,
            max_submission_cost,
        ).build_transaction(
            {
                "from": from_address,
                "gas": 222780,  # Explicitly set gas to avoid automatic estimation
                "gasPrice": Web3.to_wei("21", "gwei"),
                "value": gas_limit * max_fee_per_gas + max_submission_cost,
            }
        )
        return transaction_data

    async def set_gateways(
        self,
        l1_signer: SignerOrProvider,
        l2_provider: Web3,
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
            return self._encode_set_gateways_data(
                token_gateways=token_gateways,
                params=params,
                l1_gateway_router=l1_gateway_router,
                from_address=from_address,
            )

        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await g_estimator.populate_function_params(
            set_gateways_func, l1_signer.provider, options
        )
        transaction = {
            "to": Web3.to_checksum_address(estimates["to"]),
            "data": estimates["data"],
            "value": int(estimates["estimates"]["deposit"]),
        }

        tx_hash = l1_signer.provider.eth.send_transaction(transaction)

        # Waiting for the transaction to be mined and getting the receipt
        tx_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        # Apply the monkey patch to the transaction receipt
        patched_tx_receipt = L1TransactionReceipt.monkey_patch_contract_call_wait(
            tx_receipt
        )
        return patched_tx_receipt
