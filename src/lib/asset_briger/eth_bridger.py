from web3 import Web3
from web3.contract import Contract
import json
from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.data_entities.errors import MissingProviderArbSdkError
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.data_entities.transaction_request import L2ToL1TransactionRequest, is_l1_to_l2_transaction_request, is_l2_to_l1_transaction_request
from src.lib.message.l1_to_l2_message_creator import L1ToL2MessageCreator
from src.lib.data_entities.networks import get_l2_network
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.constants import ARB_SYS_ADDRESS
from typing import Union, Optional, Dict, Any
from src.lib.utils.helper import load_contract, sign_and_sent_raw_transaction

# Not sure about the types...
EthDepositParams = Dict[str, Any]  # Replace with actual structure
L1ToL2TransactionRequest = Dict[str, Any]  # Replace with actual structure
L1EthDepositTransaction = Dict[str, Any]  # Replace with actual structure

class L1ToL2TxReqAndSigner:
    def __init__(self, l1_signer: Any, tx_request: L1ToL2TransactionRequest, overrides: Optional[Dict[str, Any]] = None):
        self.l1_signer = l1_signer
        self.tx_request = tx_request
        self.overrides = overrides or {}

class L2ToL1TxReqAndSigner:
    def __init__(self, l2_signer: Any, tx_request: L2ToL1TransactionRequest, overrides: Optional[Dict[str, Any]] = None):
        self.l2_signer = l2_signer
        self.tx_request = tx_request
        self.overrides = overrides or {}


class EthBridger(AssetBridger):
    def __init__(self, l2_network):
        super().__init__(l2_network)
        self.l2_network = l2_network

    @staticmethod
    async def from_provider(l2_provider):
        return EthBridger(await get_l2_network(l2_provider))

    async def get_deposit_request(self, params):
        inbox = load_contract(provider=params['l1Signer'].provider, contract_name='Inbox', address=self.l2_network.eth_bridge.inbox, is_classic=False)
        print(params['amount'])
        function_data = inbox.functions.depositEth().build_transaction(
            {
            }
        )['data']
        print("function_data", function_data)
        return {
            'txRequest': {
                'to': self.l2_network.eth_bridge.inbox,
                'value': params['amount'],
                'data': function_data,
                'from': params['from'],
            },
            'isValid': lambda: True
        }

    async def deposit(self, params: Union[EthDepositParams, L1ToL2TxReqAndSigner]) -> L1EthDepositTransaction:
        
        if is_l1_to_l2_transaction_request(params):
            eth_deposit = params
            # l1_signer = params.l1_signer
            # overrides = params.overrides
        else:
            eth_deposit = await self.get_deposit_request({
                **params,
                'from': params['l1Signer'].account.address,
            })
            # l1_signer = params['l1Signer']
            # overrides = params.get('overrides', {})

        tx = {
            **eth_deposit['txRequest'],
            **params.get('overrides', {})
        }

        gas_estimate = params['l1Signer'].provider.eth.estimate_gas(tx)

        tx['gas'] = gas_estimate
        tx['gasPrice'] = params['l1Signer'].provider.eth.gas_price
        tx['nonce'] = params['l1Signer'].provider.eth.get_transaction_count(params['l1Signer'].account.address)
        tx['chainId'] = params['l1Signer'].provider.eth.chain_id

        signed_tx = params['l1Signer'].account.sign_transaction(tx)

        # Send the raw transaction
        tx_hash = params['l1Signer'].provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        tx_receipt = params['l1Signer'].provider.eth.wait_for_transaction_receipt(tx_hash)


        print('params',tx_receipt)
        # tx_receipt = sign_and_sent_raw_transaction(params['l1Signer'], tx_receipt)

        return L1TransactionReceipt.monkey_patch_eth_deposit_wait(tx_receipt)

    async def get_deposit_to_request(self, params):
        request_params = {
            **params,
            'to': params['destinationAddress'],
            'l2CallValue': params['amount'],
            'callValueRefundAddress': params['destinationAddress'],
            'data': '0x',
        }
        gas_overrides = params.get('retryableGasOverrides', {})
        return await L1ToL2MessageCreator.get_ticket_creation_request(
            request_params, params['l1Provider'], params['l2Provider'], gas_overrides
        )

    async def deposit_to(self, params):
        await self.check_l1_network(params['l1Signer'])
        await self.check_l2_network(params['l2Provider'])

        if is_l1_to_l2_transaction_request(params):
            retryable_ticket_request = params
        else:
            retryable_ticket_request = await self.get_deposit_to_request({
                **params,
                'from': params['l1Signer'].account.address,
                'l1Provider': params['l1Signer'].provider}
                )
        
        tx = {
            **retryable_ticket_request['txRequest'],
            **params.get('overrides', {})
        }

        gas_estimate = params['l1Signer'].provider.eth.estimate_gas(tx)

        tx['gas'] = gas_estimate
        tx['gasPrice'] = params['l1Signer'].provider.eth.gas_price
        tx['nonce'] = params['l1Signer'].provider.eth.get_transaction_count(params['l1Signer'].account.address)
        tx['chainId'] = params['l1Signer'].provider.eth.chain_id

        signed_tx = params['l1Signer'].account.sign_transaction(tx)

        # Send the raw transaction
        tx_hash = params['l1Signer'].provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        tx_receipt = params['l1Signer'].provider.eth.wait_for_transaction_receipt(tx_hash)

        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)

    async def get_withdrawal_request(self, params):
        print('params', params)
        arb_sys = load_contract(provider=params['l2Signer'].provider, contract_name='ArbSys', address=ARB_SYS_ADDRESS, is_classic=False)

        function_data = arb_sys.encodeABI(
            fn_name="withdrawEth",
            args=[
                params['destinationAddress']
            ],
        )

        return {
            'txRequest': {
                'to': ARB_SYS_ADDRESS,
                'data': function_data,
                'value': params['amount'],
                'from': params['from'],
            },
            'estimateL1GasLimit': lambda _: 130000
        }

    async def withdraw(self, params):

        if(not SignerProviderUtils.signer_has_provider(params['l2Signer'])):
            raise MissingProviderArbSdkError('l2Signer')
        
        await self.check_l2_network(params['l2Signer'])

        if is_l2_to_l1_transaction_request(params):
            request = params
        else:
            request = await self.get_withdrawal_request(params)

        tx = {
            **request['txRequest'],
            **params.get('overrides', {})
        }

        gas_estimate = params['l2Signer'].provider.eth.estimate_gas(tx)

        tx['gas'] = gas_estimate
        tx['gasPrice'] = params['l2Signer'].provider.eth.gas_price
        tx['nonce'] = params['l2Signer'].provider.eth.get_transaction_count(params['l2Signer'].account.address)

        signed_tx = params['l2Signer'].account.sign_transaction(tx)

        # Send the raw transaction
        tx_hash = params['l2Signer'].provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        tx_receipt = params['l2Signer'].provider.eth.wait_for_transaction_receipt(tx_hash)

        return L2TransactionReceipt.monkey_patch_wait(tx_receipt)
