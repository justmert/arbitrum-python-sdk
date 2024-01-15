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
from src.lib.utils.helper import load_contract
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.data_entities.transaction_request import is_l1_to_l2_transaction_request, is_l2_to_l1_transaction_request
from src.lib.data_entities.networks import L1Network, L2Network, EthBridge, TokenBridge

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
        l1_gateway_router = load_contract(provider=l1_provider, contract_name='L1GatewayRouter', address=self.l2_network.token_bridge.l1_gateway_router, is_classic=True)
        return await l1_gateway_router.get_gateway(erc20_l1_address)

    async def get_l2_gateway_address(self, erc20_l1_address, l2_provider):
        await self.check_l2_network(l2_provider)
        l2_gateway_router = load_contract(provider=l2_provider, contract_name='L2GatewayRouter', address=self.l2_network.token_bridge.l2_gateway_router, is_classic=True)
        return await l2_gateway_router.get_gateway(erc20_l1_address)

    async def get_approve_token_request(self, params):
        gateway_address = await self.get_l1_gateway_address(params['erc20L1Address'], SignerProviderUtils.get_provider_or_throw(params['l1Provider']))
        i_erc20_interface = load_contract(provider=params['l1Provider'], contract_name='ERC20', address=params['erc20L1Address'], is_classic=True)
        # i_erc20_interface = ERC20.create_interface()
        data = i_erc20_interface.encode_function_data('approve', [gateway_address, params.get('amount', MAX_APPROVAL)])
        return {'to': params['erc20L1Address'], 'data': data, 'value': 0}

    async def approve_token(self, params):
        await self.check_l1_network(params['l1Signer'])
        approve_request = await self.get_approve_token_request(params) if SignerProviderUtils.get_provider_or_throw(params['l1Signer']) else params['txRequest']
        return await params['l1Signer'].send_transaction({**approve_request, **params.get('overrides', {})})

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
            params['amount'],
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
        if not SignerProviderUtils.signer_has_provider(params['l1Signer']):
            raise MissingProviderArbSdkError('l1Signer')

        await self.check_l1_network(params['l1Signer'])

        l1_provider = SignerProviderUtils.get_provider_or_throw(params['l1Signer'])

        # Determine if the request is an L1 to L2 transaction request
        if is_l1_to_l2_transaction_request(params):
            token_deposit = params
        else:
            # Prepare the deposit request
            token_deposit = await self.get_deposit_request({
                **params,
                'l1Provider': l1_provider,
                'from': await params['l1Signer'].get_address()
            })

        # Send the transaction
        tx = await params['l1Signer'].send_transaction({
            **token_deposit['tx_request'],
            **params.get('overrides', {})
        })
        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx)


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
