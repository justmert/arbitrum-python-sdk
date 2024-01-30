from web3 import Web3
from web3.contract import Contract
import json
from src.lib.asset_briger.asset_bridger import AssetBridger
from src.lib.data_entities.transaction_request import L2ToL1TransactionRequest
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

        function_data = inbox.functions.depositEth().build_transaction(
            {

            }
        )['data']
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
        if isinstance(params, L1ToL2TxReqAndSigner):
            eth_deposit = params.tx_request
            l1_signer = params.l1_signer
            overrides = params.overrides
        else:
            eth_deposit = await self.get_deposit_request({
                **params,
                'from': params['l1Signer'].account.address,
            })
            l1_signer = params['l1Signer']
            overrides = params.get('overrides', {})

        tx = {
            **eth_deposit['txRequest'],
            **overrides
        }
        print('params',tx)
        tx_receipt = sign_and_sent_raw_transaction(l1_signer, tx)

        return L1TransactionReceipt.monkey_patch_eth_deposit_wait(tx_receipt)

    async def get_deposit_to_request(self, params):
        request_params = {
            **params,
            'to': params.destinationAddress,
            'l2CallValue': params.amount,
            'callValueRefundAddress': params.destinationAddress,
            'data': '0x',
        }
        gas_overrides = params.retryableGasOverrides or {}
        return await L1ToL2MessageCreator.get_ticket_creation_request(
            request_params, params.l1Provider, params.l2Provider, gas_overrides
        )

    async def deposit_to(self, params):
        if isinstance(params, L1ToL2TxReqAndSigner):
            retryable_ticket_request = params
        else:
            retryable_ticket_request = await self.get_deposit_to_request(params)
        tx = params.l1Signer.send_transaction({
            **retryable_ticket_request.txRequest,
            **params.overrides
        })
        return L1TransactionReceipt.monkey_patch_contract_call_wait(tx)

    async def get_withdrawal_request(self, params):
        arb_sys = load_contract(provider=self.l2_provider, contract_name='ArbSys', address=ARB_SYS_ADDRESS) # also available in classic!
        function_data = arb_sys.encodeFunctionData('withdrawEth', [params.destinationAddress])
        return {
            'txRequest': {
                'to': ARB_SYS_ADDRESS,
                'data': function_data,
                'value': Web3.to_wei(params.amount, 'ether'),
                'from': params['from'],
            },
            'estimateL1GasLimit': lambda l1_provider: 130000
        }

    async def withdraw(self, params):
        if isinstance(params, L2ToL1TxReqAndSigner):
            request = params
        else:
            request = await self.get_withdrawal_request(params)
        tx = params.l2Signer.send_transaction({
            **request.txRequest,
            **params.overrides
        })
        return L2TransactionReceipt.monkey_patch_wait(tx)
