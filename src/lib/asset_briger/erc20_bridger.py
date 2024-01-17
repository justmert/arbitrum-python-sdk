from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import  SignerProviderUtils
from src.lib.data_entities.constants import DISABLED_GATEWAY
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.retryable_data import RetryableDataTools
from web3.providers import BaseProvider
from web3.contract import Contract
from web3 import Web3
from src.lib.utils.helper import CaseDict, load_contract
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.data_entities.transaction_request import is_l1_to_l2_transaction_request, is_l2_to_l1_transaction_request
from src.lib.data_entities.networks import L1Network, L2Network, EthBridge, TokenBridge
from eth_abi import encode
from web3 import Web3

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
        print('gatway_erc20', erc20_l1_address)
        print('l1_gateway_router', self.l2_network.token_bridge.l1_gateway_router)
        # l1 gateway router 0x1D55838a9EC169488D360783D65e6CD985007b72

        l1_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)
        return l1_gateway_router.functions.getGateway(erc20_l1_address).call()

    async def get_l2_gateway_address(self, erc20_l1_address, l2_provider):
        await self.check_l2_network(l2_provider)
        l2_gateway_router = load_contract(provider=l2_provider, contract_name='L2GatewayRouter', address=self.l2_network.token_bridge.l2_gateway_router, is_classic=True)
        return l2_gateway_router.functions.getGateway(erc20_l1_address).call()

    async def get_approve_token_request(self, params):
        print('aaa', SignerProviderUtils.get_provider_or_throw(params['l1Provider']))
        gateway_address = await self.get_l1_gateway_address(params['erc20L1Address'], SignerProviderUtils.get_provider_or_throw(params['l1Provider']))
        i_erc20_interface = load_contract(provider=params['l1Provider'], contract_name='ERC20', address=params['erc20L1Address'], is_classic=True)

        # Encode the function call
        data = i_erc20_interface.functions.approve(gateway_address, params.get('amount', MAX_APPROVAL)).build_transaction({
            # 'from': w3.eth.default_account  # This needs to be the account that will send the transaction
        })['data']
        return {'to': params['erc20L1Address'], 'data': data, 'value': 0}

    async def approve_token(self, params):
        await self.check_l1_network(params['l1Provider'])
        approve_request = await self.get_approve_token_request(params) if SignerProviderUtils.get_provider_or_throw(params['l1Signer']) else params['txRequest']
    
        
        # Merge any overrides
        transaction = {**approve_request, **params.get('overrides', {
            'gasPrice': Web3.to_wei('21', 'gwei')
        })}

        # Estimate gas and set the transaction parameters
        transaction['gas'] = params['l1Provider'].eth.estimate_gas(transaction)
        transaction['nonce'] = params['l1Provider'].eth.get_transaction_count(params['l1Signer'].address)
        transaction['chainId'] = params['l1Provider'].eth.chain_id
        print(transaction)
        # Sign the transaction
        signed_txn = params['l1Signer'].sign_transaction(transaction)

        # Send the transaction
        tx_hash = params['l1_provider'].eth.send_raw_transaction(signed_txn.rawTransaction)

        # Wait for the transaction to be mined
        tx_receipt = params['l1_provider'].eth.wait_for_transaction_receipt(tx_hash)

        return tx_receipt

    async def get_l2_withdrawal_events(self, l2_provider, gateway_address, filter, l1_token_address = None, from_address = None, to_address = None):
        await self.check_l2_network(l2_provider)
        event_fetcher = EventFetcher(l2_provider)
        l2_arbitrum_gateway = load_contract(provider=l2_provider, contract_name='L2ArbitrumGateway', address=gateway_address, is_classic=True)
        events = await event_fetcher.get_events(l2_arbitrum_gateway.abi, lambda contract: contract.filters.WithdrawalInitiated(None, from_address, to_address), {**filter, 'address': gateway_address})
        return [event for event in events if event.l1Token.lower() == l1_token_address.lower()] if l1_token_address else events


    async def looks_like_weth_gateway(self, potential_weth_gateway_address, l1_provider):
        try:   
            potential_weth_gateway = load_contract(provider=l1_provider, contract_name='L1WethGateway', address=potential_weth_gateway_address, is_classic=True)
            # potential_weth_gateway = L1WethGateway(potential_weth_gateway_address, l1_provider)
            await potential_weth_gateway.functions.l1Weth().call()
            return True
        except Exception as err:
            if isinstance(err, Web3.exceptions.ContractLogicError) and 'CALL_EXCEPTION' in str(err):
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

    def get_l2_token_contract(self, l2_provider, l2_token_addr):
        return load_contract(provider=l2_provider, contract_name='L2GatewayToken', address=l2_token_addr, is_classic=True)

    def get_l1_token_contract(self, l1_provider, l1_token_addr):
        return load_contract(provider=l1_provider, contract_name='ERC20', address=l1_token_addr, is_classic=True)

    async def get_l2_erc20_address(self, erc20_l1_address, l1_provider):
        await self.check_l1_network(l1_provider)
        l1_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)
        # l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return await l1_gateway_router.functions.calculateL2TokenAddress(erc20_l1_address).call()

    async def get_l1_erc20_address(self, erc20_l2_address, l2_provider):
        await self.check_l2_network(l2_provider)
        if erc20_l2_address.lower() == self.l2_network.token_bridge.l2_weth.lower():
            return self.l2_network.token_bridge.l1_weth
        arb_erc20 = load_contract(provider=l2_provider, contract_name='L2GatewayToken', address=erc20_l2_address, is_classic=True)
        # arb_erc20 = L2GatewayToken(erc20_l2_address, l2_provider)
        l1_address = await arb_erc20.functions.l1Address().call()
        l2_gateway_router = load_contract(provider=l2_provider, contract_name='L2GatewayRouter', address=self.l2_network.token_bridge.l2_gateway_router, is_classic=True)
        # l2_gateway_router = L2GatewayRouter(self.l2_network.token_bridge.l2_gateway_router, l2_provider)
        l2_address = await l2_gateway_router.calculateL2TokenAddress(l1_address).call()
        if l2_address.lower() != erc20_l2_address.lower():
            raise ArbSdkError(f"Unexpected l1 address. L1 address from token is not registered to the provided l2 address. {l1_address} {l2_address} {erc20_l2_address}")
        return l1_address

    async def l1_token_is_disabled(self, l1_token_address, l1_provider):
        await self.check_l1_network(l1_provider)
        l1_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)
        # l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return (await l1_gateway_router.l1TokenToGateway(l1_token_address).call()) == DISABLED_GATEWAY

    def apply_defaults(self, params):
        return {
            **params,
            'excessFeeRefundAddress': params.get('excessFeeRefundAddress', params['from']),
            'callValueRefundAddress': params.get('callValueRefundAddress', params['from']),
            'destinationAddress': params.get('destinationAddress', params['from']),
        }

    async def get_withdrawal_request(self, params):
        to_address = params['destination_address']
        router_interface = load_contract(provider=params['l2Provider'], contract_name='L2GatewayRouter', address=self.l2_network.token_bridge.l2_gateway_router, is_classic=True)
        # router_interface = L2GatewayRouter.create_interface()  # Make sure to implement create_interface
        function_data = router_interface.encodeFunctionData('outboundTransfer(address,address,uint256,bytes)', [
            params['erc20l1_address'],
            to_address,
            int(params['amount']),
            '0x',
        ])
        
        l1_gateway_address = await self.get_l1_gateway_address(params['erc20l1_address'], params['l1_provider'])
        is_weth = await self.is_weth_gateway(l1_gateway_address, params['l1_provider'])
        gas_estimate = Web3.toInt(180000) if is_weth else Web3.toInt(160000)

        return {
            'tx_request': {
                'data': function_data,
                'to': self.l2_network.token_bridge.l2_gateway_router,
                'value': Web3.toInt(0),
                'from': params['from'],
            },
            'estimate_l1_gas_limit': gas_estimate  # This is a placeholder, replace with actual estimation logic.
        }



    async def _estimate_l1_gas_limit(self, l1_provider, params):
        l1_gateway_address = await self.get_l1_gateway_address(params['erc20l1Address'], l1_provider)
        is_weth = await self.is_weth_gateway(l1_gateway_address, l1_provider)
        return 180000 if is_weth else 160000

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params['l2Signer']):
            raise MissingProviderArbSdkError('l2Signer')
        await self.check_l2_network(params['l2Signer'])

        withdrawal_request = params if SignerProviderUtils.signer_has_provider(params['l2Signer'])  else await self.get_withdrawal_request({
            **params,
            'from': await params['l2Signer'].get_address()
        })

        tx = await params['l2Signer'].send_transaction({
            **withdrawal_request['txRequest'],
            **params.get('overrides', {})
        })
        return L2TransactionReceipt.monkey_patch_wait(tx)



    async def deposit(self, params):
        if not SignerProviderUtils.signer_has_provider(params['l1_signer']):
            raise MissingProviderArbSdkError('l1Signer')

        await self.check_l1_network(params['l1Signer'])

        l1_provider = SignerProviderUtils.get_provider_or_throw(params['l1Provider'])

        print('deposit_params', params)
        # Determine if the request is an L1 to L2 transaction request
        if is_l1_to_l2_transaction_request(params):
            token_deposit = params
        else:
            # Prepare the deposit request
            token_deposit = await self.get_deposit_request(
                {
                    **params,
                    'from': params['l1Signer'].address
                },
                l1_provider=l1_provider,
                l2_provider=params['l2Provider']
            )

        # Send the transaction
        # tx = await params['l1Signer'].send_transaction({
        #     **token_deposit['tx_request'],
        #     **params.get('overrides', {})
        # })
        # return L1TransactionReceipt.monkey_patch_contract_call_wait(tx)
        # Combine with overrides
        transaction = {**token_deposit['tx_request'], **params.get('overrides', {
            'gasPrice': Web3.to_wei('21', 'gwei')
        })}



        transaction['value'] = int(transaction['value']) if 'value' in transaction else 0
        # Estimate gas and set the transaction parameters
        transaction['gas'] = l1_provider.eth.estimate_gas(transaction)
        transaction['nonce'] = l1_provider.eth.get_transaction_count(params['l1Signer'].address)
        transaction['chainId'] = l1_provider.eth.chain_id
        print('transaction', transaction)
        # Sign the transaction with the private key
        signed_txn = params['l1Signer'].sign_transaction(transaction)

        # Send the transaction
        tx_hash = params['l1Provider'].eth.send_raw_transaction(signed_txn.rawTransaction)

        # Wait for the transaction to be mined and get the receipt
        tx_receipt = params['l1Provider'].eth.wait_for_transaction_receipt(tx_hash)

        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)


    def solidity_encode(self, types, values):
        # Correctly handle '0x' string to be an empty byte string
        values = [val if val != '0x' else b'' for val in values]
        
        # ABI encode the values
        encoded_values = encode(types, values)
        return encoded_values

    async def get_deposit_request(self, params, l1_provider, l2_provider):
        # Check networks
        # Implement checkL1Network and checkL2Network
        await self.check_l1_network(l1_provider)
        await self.check_l2_network(l2_provider)

        # Apply defaults to the parameters
        # Implement apply_defaults
        defaulted_params = CaseDict(self.apply_defaults(params))
        # print('def_aparams', defaulted_params)

        # Extract necessary parameters
        amount = defaulted_params['amount']
        destination_address = defaulted_params['destination_address']
        erc20_l1_address = defaulted_params['erc20_l1_address']
        retryable_gas_overrides = defaulted_params.get('retryable_gas_overrides', {})

        # Get L1 gateway address
        l1_gateway_address = await self.get_l1_gateway_address(erc20_l1_address, l1_provider)

        # Adjust for custom gateway deposits
        if l1_gateway_address == self.l2_network.tokenBridge.l1CustomGateway:
            if 'gasLimit' not in retryable_gas_overrides:
                retryable_gas_overrides['gasLimit'] = {}
            if 'min' not in retryable_gas_overrides['gasLimit']:
                retryable_gas_overrides['gasLimit']['min'] = MIN_CUSTOM_DEPOSIT_GAS_LIMIT

        # Define deposit function
        def deposit_func(deposit_params):
            print(deposit_params['maxSubmissionCost'])
            inner_data = self.solidity_encode(['uint256', 'bytes'], [int(deposit_params['maxSubmissionCost']), "0x"])
            # i_gateway_router = load_contract(contract_name='L1GatewayRouter')
            i_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)
        # Get the contract function
            # Create encoded data for the function call

            print('------start-')
            print('gaslimit', deposit_params['gasLimit'])
            print('maxfeepergas', deposit_params['maxFeePerGas'])
            print('------end-')
            encoded_data = i_gateway_router.functions.outboundTransfer(
                Web3.to_checksum_address(erc20_l1_address), 
                Web3.to_checksum_address(destination_address), 
                int(amount), 
                int(deposit_params['gasLimit']), 
                int(deposit_params['maxFeePerGas']), 
                inner_data
            ).build_transaction({
                'from': defaulted_params['from'],
                'gas': 222780,  # Explicitly set gas to avoid automatic estimation
                'gasPrice': Web3.to_wei('21', 'gwei'),
                'value': deposit_params['gasLimit'] * deposit_params['maxFeePerGas'] + deposit_params['maxSubmissionCost']

            })
            return encoded_data

        
        # Estimate gas
        gas_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await gas_estimator.populate_function_params(deposit_func, l1_provider, retryable_gas_overrides)
        print('estimates', estimates)
        print('o1o1o1o1o1o1oo1o1o1o1oo1o1o')
        return {
            'tx_request': {
                'to': self.l2_network.tokenBridge.l1GatewayRouter,
                'data': estimates['data'],
                'value': estimates['value'],
                'from': params['from']
            },
            'retryable_data': {
                **estimates['retryable'],
                **estimates['estimates']
            },
            'is_valid': lambda: L1ToL2MessageGasEstimator.is_valid(estimates['estimates'], re_estimates['estimates'])
        }


class AdminErc20Bridger(Erc20Bridger):
    async def register_custom_token(
        self, l1_token_address, l2_token_address,
        l1_signer, l2_provider
    ) -> Contract:
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError('l1Signer')
        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        l1_sender_address = await l1_signer.get_address()
        print('admin_erc20_bridger')
        l1_token = load_contract(provider=l1_signer, contract_name='ICustomToken', address=l1_token_address, is_classic=True)
        # l1_token = ICustomToken(l1_token_address, l1_signer)
        l2_token = load_contract(provider=l2_provider, contract_name='IArbToken', address=l2_token_address, is_classic=True)
        # l2_token = IArbToken(l2_token_address, l2_provider)

        # Sanity checks
        if not l1_token.is_deployed():
            raise ArbSdkError('L1 token is not deployed.')
        if not l2_token.is_deployed():
            raise ArbSdkError('L2 token is not deployed.')

        l1_address_from_l2 = await l2_token.l1_address()
        if l1_address_from_l2 != l1_token_address:
            raise ArbSdkError(
                f"L2 token does not have l1 address set. Set address: {l1_address_from_l2}, expected address: {l1_token_address}."
            )
        print('admin_erc20_bridger1')
        from_address = await l1_signer.get_address()
        encode_func_data = self._encode_func_data

        l1_provider = l1_signer.provider
        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        set_token_estimates2 = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                set_token_gas={
                    'gasLimit': params['gasLimit'],
                    'maxSubmissionCost': params['maxSubmissionCost'],
                },
                set_gateway_gas={
                    'gasLimit': RetryableDataTools.ErrorTriggeringParams['gasLimit'],
                    'maxSubmissionCost': 1,
                },
                max_fee_per_gas=params['maxFeePerGas']
            ),
            l1_provider
        )
        print('admin_erc20_bridger2')
        set_gateway_estimates2 = await g_estimator.populate_function_params(
            lambda params: encode_func_data(
                set_token_gas=set_token_estimates2['estimates'],
                set_gateway_gas={
                    'gasLimit': params['gasLimit'],
                    'maxSubmissionCost': params['maxSubmissionCost'],
                },
                max_fee_per_gas=params['maxFeePerGas']
            ),
            l1_provider
        )

        register_tx = await l1_signer.send_transaction({
            'to': l1_token.address,
            'data': set_gateway_estimates2['data'],
            'value': set_gateway_estimates2['value'],
        })
        print('admin_erc20_bridger3')
        return L1TransactionReceipt.monkey_patch_contract_call_wait(register_tx)


    async def get_l1_gateway_set_events(
        self, l1_provider,
        filter,
        custom_network_l1_gateway_router = None
    ) -> list:
        # if self.l2_network.is_custom and not custom_network_l2_gateway_router:
        #     raise ArbSdkError('Must supply customNetworkL2GatewayRouter for custom network ')
        await self.check_l1_network(l1_provider)

        l1_gateway_router_address = custom_network_l1_gateway_router or self.l2_network.token_bridge.l1_gateway_router
        event_fetcher = EventFetcher(l1_provider)
        L1GatewayRouter = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=l1_gateway_router_address, is_classic=True)
        events = await event_fetcher.get_events(
            L1GatewayRouter,
            lambda t: t.filters.GatewaySet(),
            {**filter, 'address': l1_gateway_router_address}
        )
        return [a['event'] for a in events]


    async def get_l2_gateway_set_events(
        self, l2_provider,
        filter,
        custom_network_l2_gateway_router = None
    ) -> list:
        # if self.l2_network.is_custom and not custom_network_l2_gateway_router:
        #     raise ArbSdkError('Must supply customNetworkL2GatewayRouter for custom network ')
        await self.check_l2_network(l2_provider)

        l2_gateway_router_address = custom_network_l2_gateway_router or self.l2_network.token_bridge.l2_gateway_router
        event_fetcher = EventFetcher(l2_provider)
        L2GatewayRouter = load_contract(provider=l2_provider, contract_name='L2GatewayRouter', address=l2_gateway_router_address, is_classic=True)
        events = await event_fetcher.get_events(
            L2GatewayRouter,
            lambda t: t.filters.GatewaySet(),
            {**filter, 'address': l2_gateway_router_address}
        )
        return [a['event'] for a in events]

    def _encode_set_gateways_data(self, token_gateways, params, l1_gateway_router, from_address):
        # Construct the transaction data for setting gateways
        token_addresses = [gateway['tokenAddr'] for gateway in token_gateways]
        gateway_addresses = [gateway['gatewayAddr'] for gateway in token_gateways]

        # Ensure token_addresses and gateway_addresses are lists of string addresses
        if all(isinstance(token_address, str) for token_address in token_addresses):
            token_addresses = [Web3.to_checksum_address(token_address) for token_address in token_addresses]
        
        elif all(isinstance(token_address, Contract) for token_address in token_addresses):
            token_addresses = [Web3.to_checksum_address(gateway['tokenAddr'].address) for gateway in token_gateways]
        
        else:
            raise ArbSdkError('token_addresses must be lists of string addresses or Contract instances.')
        
        if all(isinstance(gateway_address, str) for gateway_address in gateway_addresses):
            gateway_addresses = [Web3.to_checksum_address(gateway_address) for gateway_address in gateway_addresses]
        
        elif all(isinstance(gateway_address, Contract) for gateway_address in gateway_addresses):
            gateway_addresses = [Web3.to_checksum_address(gateway['gatewayAddr'].address) for gateway in token_gateways]

        else:
            raise ArbSdkError('gateway_addresses must be lists of string addresses or Contract instances.')

        # Convert integer values to Web3 BigNumber format
        gas_limit = int(params['gasLimit'])
        max_fee_per_gas = int(params['maxFeePerGas'])
        max_submission_cost = int(params['maxSubmissionCost'])

        transaction_data = l1_gateway_router.functions.setGateways(
                token_addresses,
                gateway_addresses,
                gas_limit,
                max_fee_per_gas,
                max_submission_cost
            ).build_transaction({
                'from': from_address,
                'gas': 222780,  # Explicitly set gas to avoid automatic estimation
                'gasPrice': Web3.to_wei('21', 'gwei'),
                'value': gas_limit * max_fee_per_gas + max_submission_cost
            })
        return transaction_data

    async def set_gateways(
        self, l1_signer, l1_provider: Web3, l2_signer, l2_provider: Web3, 
        token_gateways, options=None
    ):
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError('l1Signer')
        
        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        from_address = l1_signer.address

        l1_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)

        def set_gateways_func(params):
            return self._encode_set_gateways_data(token_gateways=token_gateways, params=params, l1_gateway_router=l1_gateway_router, from_address=from_address)

        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await g_estimator.populate_function_params(
            set_gateways_func, 
            l1_provider, 
            options
        )
        transaction = {
            'to':  Web3.to_checksum_address(estimates['to']),
            'data': estimates['data'],
            'value': int(estimates['estimates']['deposit']),
        }
    
        tx_hash = l1_provider.eth.send_transaction(transaction)

        # Waiting for the transaction to be mined and getting the receipt
        tx_receipt = l1_provider.eth.wait_for_transaction_receipt(tx_hash)

        # Apply the monkey patch to the transaction receipt
        patched_tx_receipt = L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)
        return patched_tx_receipt
