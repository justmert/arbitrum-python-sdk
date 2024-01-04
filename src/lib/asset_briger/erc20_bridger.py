from typing import Optional, TypedDict, Union, List
from eth_typing import ChecksumAddress
# Custom imports based on your project structure, may need adjustment


# from abi import L1GatewayRouter, L2GatewayRouter, L1WethGateway, L2ArbitrumGateway, ERC20, L2GatewayToken, ICustomToken, IArbToken
# from abi import L1GatewayRouter, L2GatewayRouter, L2ArbitrumGateway
# from abi import L1WethGateway, L2GatewayToken, L1GatewayRouter, L2GatewayRouter
# from abi import L2GatewayRouter, ICustomToken, IArbToken
# from abi import L1GatewayRouter, L1ToL2MessageGasEstimator, EventFetcher

from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerOrProvider, SignerProviderUtils
from src.lib.message.l1_transaction import L1ContractTransaction
from src.lib.message.l2_transaction import L2ContractTransaction
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.message.l2_to_l1_message_classic import ClassicL2ToL1TransactionEvent
from src.lib.message.l2_to_l1_message_nitro import NitroL2ToL1TransactionEvent
from src.lib.utils.lib import is_defined
from src.lib.data_entities.message import L2ToL1MessageStatus
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from typing import Optional, List, Dict, Union
from web3 import Web3
from src.lib.data_entities.networks import L2Network, L1Network
from src.lib.data_entities.constants import DISABLED_GATEWAY
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.asset_briger.eth_bridger import EthDepositParams, EthWithdrawParams
from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.transaction_request import L1ToL2MessageGasParams, L1ToL2TransactionRequest, L1ToL2MessageParams, L2ToL1TransactionRequest
from src.lib.data_entities.retryable_data import RetryableDataTools, RetryableData
from src.lib.data_entities.event import EventArgs
from src.lib.data_entities.transaction_request import is_l1_to_l2_transaction_request, is_l2_to_l1_transaction_request
from web3.providers import BaseProvider
from web3.contract import Contract
from data_entities import ArbSdkError, L1ToL2MessageGasEstimator, SignerProviderUtils
from utils import get_provider_or_throw, encode_function_data
import json
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams, BlockIdentifier, TxReceipt, BlockData
from src.lib.utils.helper import load_contract
import asyncio



MAX_APPROVAL = 2**256 - 1
MIN_CUSTOM_DEPOSIT_GAS_LIMIT = 275000

# Constants
MAX_UINT256 = 2**256 - 1

# class TokenApproveParams(TypedDict):
#     erc20L1Address: ChecksumAddress
#     amount: Optional[int]  # Replace with your BigNumber library if needed
#     overrides: Optional[TxParams]

# class Erc20DepositParams(EthDepositParams):
#     l2Provider: BaseProvider
#     erc20L1Address: ChecksumAddress
#     destinationAddress: Optional[ChecksumAddress]
#     excessFeeRefundAddress: Optional[ChecksumAddress]
#     callValueRefundAddress: Optional[ChecksumAddress]
#     retryableGasOverrides: Optional[GasOverrides]
#     overrides: Optional[TxParams]

# class Erc20WithdrawParams(EthWithdrawParams):
#     erc20l1Address: ChecksumAddress

# class L1ToL2TxReqAndSignerProvider(L1ToL2TransactionRequest):
#     l1Signer: Signer  # Replace with your Signer object
#     overrides: Optional[TxParams]

# class L2ToL1TxReqAndSigner(L2ToL1TransactionRequest):
#     l2Signer: Signer  # Replace with your Signer object
#     overrides: Optional[TxParams]

# class SignerTokenApproveParams(TokenApproveParams):
#     l1Signer: Signer  # Replace with your Signer object

# class ProviderTokenApproveParams(TokenApproveParams):
#     l1Provider: BaseProvider

# ApproveParamsOrTxRequest = Union[
#     SignerTokenApproveParams,
#     TypedDict('TxRequestWithSigner', {
#         'txRequest': Required[TxParams, ['to', 'data', 'value']],
#         'l1Signer': Signer,  # Replace with your Signer object
#         'overrides': Optional[TxParams]
#     })
# ]

# class DepositRequest(OmitTyped[Erc20DepositParams, 'overrides', 'l1Signer']):
#     l1Provider: BaseProvider
#     from_address: ChecksumAddress

# class DefaultedDepositRequest(RequiredPick[DepositRequest, 'callValueRefundAddress', 'excessFeeRefundAddress', 'destinationAddress']):
#     pass

# Implement the classes and functions based on the logic provided in the TypeScript code.
# This translation provides a structured base to work on.
# Make sure to replace custom types like `Signer` with appropriate objects from the web3.py library or your custom implementation.
# Adjust the import paths and other details based on your specific project structure and requirements.

class Erc20Bridger(AssetBridger):
    def __init__(self, l2_network: L2Network):
        super().__init__(l2_network)

    @classmethod
    async def from_provider(cls, l2_provider: BaseProvider):
        l2_network = await get_l2_network(l2_provider)
        return cls(l2_network)

    async def get_l1_gateway_address(self, erc20_l1_address: ChecksumAddress, l1_provider: BaseProvider) -> ChecksumAddress:
        await self.check_l1_network(l1_provider)
        l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return await l1_gateway_router.get_gateway(erc20_l1_address)

    async def get_l2_gateway_address(self, erc20_l1_address: ChecksumAddress, l2_provider: BaseProvider) -> ChecksumAddress:
        await self.check_l2_network(l2_provider)
        l2_gateway_router = L2GatewayRouter(self.l2_network.token_bridge.l2_gateway_router, l2_provider)
        return await l2_gateway_router.get_gateway(erc20_l1_address)

    async def get_approve_token_request(self, params: ProviderTokenApproveParams) -> TxParams:
        gateway_address = await self.get_l1_gateway_address(params['erc20L1Address'], get_provider_or_throw(params['l1Provider']))
        i_erc20_interface = ERC20.create_interface()
        data = i_erc20_interface.encode_function_data('approve', [gateway_address, params.get('amount', MAX_APPROVAL)])
        return {'to': params['erc20L1Address'], 'data': data, 'value': 0}

    async def approve_token(self, params: ApproveParamsOrTxRequest) -> 'ContractTransaction':
        await self.check_l1_network(params['l1Signer'])
        approve_request = await self.get_approve_token_request(params) if is_signer_token_approve_params(params) else params['txRequest']
        return await params['l1Signer'].send_transaction({**approve_request, **params.get('overrides', {})})

    async def get_l2_withdrawal_events(self, l2_provider: BaseProvider, gateway_address: ChecksumAddress, filter: dict, l1_token_address: Optional[ChecksumAddress] = None, from_address: Optional[ChecksumAddress] = None, to_address: Optional[ChecksumAddress] = None) -> List[EventArgs[WithdrawalInitiatedEvent]]:
        await self.check_l2_network(l2_provider)
        event_fetcher = EventFetcher(l2_provider)
        events = await event_fetcher.get_events(L2ArbitrumGateway, lambda contract: contract.filters.WithdrawalInitiated(None, from_address, to_address), {**filter, 'address': gateway_address})
        return [event for event in events if event.l1Token.lower() == l1_token_address.lower()] if l1_token_address else events


    async def looks_like_weth_gateway(self, potential_weth_gateway_address: ChecksumAddress, l1_provider: BaseProvider) -> bool:
        try:
            potential_weth_gateway = L1WethGateway(potential_weth_gateway_address, l1_provider)
            await potential_weth_gateway.functions.l1Weth().call()
            return True
        except Exception as err:
            if isinstance(err, Web3.exceptions.ContractLogicError) and 'CALL_EXCEPTION' in str(err):
                return False
            else:
                raise err

    async def is_weth_gateway(self, gateway_address: ChecksumAddress, l1_provider: BaseProvider) -> bool:
        weth_address = self.l2_network.token_bridge.l1_weth_gateway
        if self.l2_network.is_custom:
            if await self.looks_like_weth_gateway(gateway_address, l1_provider):
                return True
        elif weth_address == gateway_address:
            return True
        return False

    def get_l2_token_contract(self, l2_provider: BaseProvider, l2_token_addr: ChecksumAddress) -> Contract:
        return L2GatewayToken(l2_token_addr, l2_provider)

    def get_l1_token_contract(self, l1_provider: BaseProvider, l1_token_addr: ChecksumAddress) -> Contract:
        return ERC20(l1_token_addr, l1_provider)

    async def get_l2_erc20_address(self, erc20_l1_address: ChecksumAddress, l1_provider: BaseProvider) -> ChecksumAddress:
        await self.check_l1_network(l1_provider)
        l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return await l1_gateway_router.functions.calculateL2TokenAddress(erc20_l1_address).call()

    async def get_l1_erc20_address(self, erc20_l2_address: ChecksumAddress, l2_provider: BaseProvider) -> ChecksumAddress:
        await self.check_l2_network(l2_provider)
        if erc20_l2_address.lower() == self.l2_network.token_bridge.l2_weth.lower():
            return self.l2_network.token_bridge.l1_weth
        arb_erc20 = L2GatewayToken(erc20_l2_address, l2_provider)
        l1_address = await arb_erc20.functions.l1Address().call()
        l2_gateway_router = L2GatewayRouter(self.l2_network.token_bridge.l2_gateway_router, l2_provider)
        l2_address = await l2_gateway_router.calculateL2TokenAddress(l1_address).call()
        if l2_address.lower() != erc20_l2_address.lower():
            raise ArbSdkError(f"Unexpected l1 address. L1 address from token is not registered to the provided l2 address. {l1_address} {l2_address} {erc20_l2_address}")
        return l1_address

    async def l1_token_is_disabled(self, l1_token_address: ChecksumAddress, l1_provider: BaseProvider) -> bool:
        await self.check_l1_network(l1_provider)
        l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_provider)
        return (await l1_gateway_router.l1TokenToGateway(l1_token_address).call()) == DISABLED_GATEWAY

    def apply_defaults(self, params: DepositRequest) -> DefaultedDepositRequest:
        return {
            **params,
            'excessFeeRefundAddress': params.get('excessFeeRefundAddress', params['from']),
            'callValueRefundAddress': params.get('callValueRefundAddress', params['from']),
            'destinationAddress': params.get('destinationAddress', params['from']),
        }

    async def get_withdrawal_request(self, params: Erc20WithdrawParams) -> L2ToL1TransactionRequest:
        to = params['destinationAddress']
        router_interface = L2GatewayRouter.create_interface()  # Make sure to implement create_interface
        function_data = router_interface.encode_function_data(
            'outboundTransfer(address,address,uint256,bytes)',
            [params['erc20l1Address'], to, params['amount'], '0x']
        )

        return {'txRequest': {
                'data': function_data,
                'to': self.l2_network.token_bridge.l2_gateway_router,
                'value': Web3.toWei(0, 'wei'),
                'from': params['from'],
            },
            'estimateL1GasLimit': async lambda l1_provider: self._estimate_l1_gas_limit(l1_provider, params) }


    async def _estimate_l1_gas_limit(self, l1_provider: BaseProvider, params: Erc20WithdrawParams) -> int:
        l1_gateway_address = await self.get_l1_gateway_address(params['erc20l1Address'], l1_provider)
        is_weth = await self.is_weth_gateway(l1_gateway_address, l1_provider)
        return 180000 if is_weth else 160000

    async def withdraw(self, params):
        if not SignerProviderUtils.signer_has_provider(params['l2Signer']):
            raise MissingProviderArbSdkError('l2Signer')
        await self.check_l2_network(params['l2Signer'])

        withdrawal_request = params if is_l2_to_l1_transaction_request(params) else await self.get_withdrawal_request({
            **params,
            'from': await params['l2Signer'].get_address()
        })

        tx = await params['l2Signer'].send_transaction({
            **withdrawal_request['txRequest'],
            **params.get('overrides', {})
        })
        return L2TransactionReceipt.monkey_patch_wait(tx)


class AdminErc20Bridger(Erc20Bridger):
    # ... Implement the registerCustomToken method ...

    async def register_custom_token(
        self, l1_token_address: ChecksumAddress, l2_token_address: ChecksumAddress,
        l1_signer, l2_provider: BaseProvider
    ) -> TxReceipt:
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError('l1Signer')
        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        l1_sender_address = await l1_signer.get_address()

        l1_token = ICustomToken(l1_token_address, l1_signer)
        l2_token = IArbToken(l2_token_address, l2_provider)

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

        return L1TransactionReceipt.monkey_patch_contract_call_wait(register_tx)

    async def get_l2_gateway_set_events(
        self, l2_provider: BaseProvider,
        filter: {'fromBlock': BlockIdentifier, 'toBlock': BlockIdentifier},
        custom_network_l2_gateway_router: str = None
    ) -> list:
        if self.l2_network.is_custom and not custom_network_l2_gateway_router:
            raise ArbSdkError('Must supply customNetworkL2GatewayRouter for custom network ')
        await self.check_l2_network(l2_provider)

        l2_gateway_router_address = custom_network_l2_gateway_router or self.l2_network.token_bridge.l2_gateway_router
        event_fetcher = EventFetcher(l2_provider)
        events = await event_fetcher.get_events(
            L1GatewayRouter,
            lambda t: t.filters.GatewaySet(),
            {**filter, 'address': l2_gateway_router_address}
        )
        return [a['event'] for a in events]

    async def set_gateways(
        self, l1_signer, l2_provider: BaseProvider, 
        token_gateways: list, options=None
    ) -> TxReceipt:
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError('l1Signer')
        await self.check_l1_network(l1_signer)
        await self.check_l2_network(l2_provider)

        from_address = await l1_signer.get_address()

        l1_gateway_router = L1GatewayRouter(self.l2_network.token_bridge.l1_gateway_router, l1_signer)

        set_gateways_func = lambda params: self._encode_set_gateways_data(
            token_gateways=token_gateways,
            params=params,
            l1_gateway_router=l1_gateway_router,
            from_address=from_address
        )

        g_estimator = L1ToL2MessageGasEstimator(l2_provider)
        estimates = await g_estimator.populate_function_params(set_gateways_func, l1_signer.provider, options)

        res = await l1_signer.send_transaction({
            'to': estimates['to'],
            'data': estimates['data'],
            'value': estimates['estimates']['deposit'],
        })

        return L1TransactionReceipt.monkey_patch_contract_call_wait(res)
