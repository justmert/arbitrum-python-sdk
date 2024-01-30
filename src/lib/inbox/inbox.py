from web3 import Web3
from web3.contract import Contract
from typing import Any, Dict, Tuple

from eth_abi import encode
from src.lib.message import l1_to_l2_message_gas_estimator
from src.lib.utils.helper import load_contract, sign_and_sent_raw_transaction
from src.lib.data_entities.networks import l1_networks
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.multi_call import MultiCaller
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.message import InboxMessageKind
import struct


class InboxTools:
    def __init__(self, l1_signer: Any, l2_network: Any):
        self.l1_signer = l1_signer
        self.l1_provider = SignerProviderUtils.get_provider(l1_signer)
        self.l1_network = l1_networks[l2_network.partner_chain_id]
        self.l2_network = l2_network
        if not self.l1_network:
            raise ArbSdkError(f"L1Network not found for chain id: {l2_network.partner_chain_id}.")

    async def find_first_block_below(self, block_number: int, block_timestamp: int) -> Any:
        block = await self.l1_provider.get_block(block_number)
        diff = block.timestamp - block_timestamp
        if diff < 0:
            return block

        diff_blocks = max(int(diff / self.l1_network.block_time), 10)
        return await self.find_first_block_below(block_number - diff_blocks, block_timestamp)

    def is_contract_creation(self, transaction_l2_request: Any) -> bool:
        return (
            transaction_l2_request['to'] == '0x' or
            not transaction_l2_request['to'] or
            transaction_l2_request['to'] == Web3.to_checksum_address('0x0000000000000000000000000000000000000000')
        )

    async def estimate_arbitrum_gas(self, transaction_l2_request, l2_provider) -> Dict[str, Any]:
        node_interface = load_contract(provider=l2_provider, contract_name='NodeInterface', address=NODE_INTERFACE_ADDRESS, is_classic=False) # also available in classic!
        contract_creation = self.is_contract_creation(transaction_l2_request)

        gas_components = node_interface.functions.gasEstimateComponents(
            transaction_l2_request['to'] or Web3.to_checksum_address('0x0000000000000000000000000000000000000000'),
            contract_creation,
            transaction_l2_request['data'],
            
        ).call({
                'from': transaction_l2_request['from'],
                'value': transaction_l2_request['value'],
            })
        print("gas_components", gas_components)
    #   "outputs": [
    #     {
    #       "internalType": "uint64",
    #       "name": "gasEstimate",
    #       "type": "uint64"
    #     },
    #     {
    #       "internalType": "uint64",
    #       "name": "gasEstimateForL1",
    #       "type": "uint64"
    #     },
    #     {
    #       "internalType": "uint256",
    #       "name": "baseFee",
    #       "type": "uint256"
    #     },
    #     {
    #       "internalType": "uint256",
    #       "name": "l1BaseFeeEstimate",
    #       "type": "uint256"
    #     }
    #   ],
        gas_components = {
            'gasEstimate': gas_components[0],
            'gasEstimateForL1': gas_components[1],
            'baseFee': gas_components[2],
            'l1BaseFeeEstimate': gas_components[3],
        }

        gas_estimate_for_l2 = gas_components["gasEstimate"] - gas_components["gasEstimateForL1"]
        return {**gas_components, 'gasEstimateForL2': gas_estimate_for_l2}

    async def get_force_includable_block_range(self, block_number_range_size: int) -> Dict[str, int]:
        sequencer_inbox = load_contract(provider=self.l1_provider, contract_name='SequencerInbox', address=self.l2_network.eth_bridge.sequencer_inbox, is_classic=False)
        multicall = await MultiCaller.from_provider(self.l1_provider)
        multicall_input: Tuple[
            Any, # CallInput
            Any,  # Replace Any with the actual return type from MultiCaller.getBlockNumberInput()
            Any   # Replace Any with the actual return type from MultiCaller.getCurrentBlockTimestampInput()
        ] = [
            {
                'targetAddr': sequencer_inbox.address,
                'encoder': lambda: sequencer_inbox.encode_function_data('maxTimeVariation'),
                'decoder': lambda return_data: sequencer_inbox.decode_function_result('maxTimeVariation', return_data)[0],
            },
            multicall.get_block_number_input(),
            multicall.get_current_block_timestamp_input(),
        ]

        max_time_variation, current_block_number, current_block_timestamp = await multicall.multi_call(multicall_input, True)

        first_eligible_block_number = current_block_number - max_time_variation.delay_blocks
        first_eligible_timestamp = current_block_timestamp - max_time_variation.delay_seconds

        first_eligible_block = await self.find_first_block_below(first_eligible_block_number, first_eligible_timestamp)

        return {
            'endBlock': first_eligible_block.number,
            'startBlock': first_eligible_block.number - block_number_range_size,
        }

    async def get_events_and_increase_range(self, bridge: Contract, search_range_blocks: int, 
                                                max_search_range_blocks: int, range_multiplier: int):
            e_fetcher = EventFetcher(self.l1_provider)

            capped_search_range_blocks = min(search_range_blocks, max_search_range_blocks)
            block_range = await self.get_force_includable_block_range(capped_search_range_blocks)

            events = await e_fetcher.get_events(bridge.abi, lambda b: b.filters.MessageDelivered(),
                                                {'fromBlock': block_range['startBlock'], 'toBlock': block_range['endBlock'], 'address': bridge.address})

            if events:
                return events
            elif capped_search_range_blocks == max_search_range_blocks:
                return []
            else:
                return await self.get_events_and_increase_range(bridge, search_range_blocks * range_multiplier, 
                                                                max_search_range_blocks, range_multiplier)

    async def get_force_includable_event(self, max_search_range_blocks: int = 3 * 6545,
                                        start_search_range_blocks: int = 100, range_multiplier: int = 2):
        
        bridge = load_contract(provider=self.l1_provider, contract_name='Bridge', address=self.l2_network.eth_bridge.bridge, is_classic=False)

        events = await self.get_events_and_increase_range(bridge, start_search_range_blocks, max_search_range_blocks, range_multiplier)

        if not events:
            return None

        event_info = events[-1]
        
        sequencer_inbox = load_contract(provider=self.l1_provider, contract_name='SequencerInbox', address=self.l2_network.eth_bridge.sequencer_inbox, is_classic=False)

        total_delayed_read = await sequencer_inbox.totalDelayedMessagesRead()

        if total_delayed_read > event_info.event.message_index:
            return None

        delayed_acc = await bridge.delayedInboxAccs(event_info.event.message_index)
        return {**event_info, 'delayedAcc': delayed_acc}

    async def force_include(self, message_delivered_event = None, overrides = None):
        
        sequencer_inbox = load_contract(provider=self.l1_provider, contract_name='SequencerInbox', address=self.l2_network.eth_bridge.sequencer_inbox, is_classic=False)

        event_info = message_delivered_event or await self.get_force_includable_event()

        if not event_info:
            return None

        block = await self.l1_provider.get_block(event_info.block_hash)
        return await sequencer_inbox.functions.forceInclusion(event_info.event.message_index + 1, event_info.event.kind,
                                                            [event_info.block_number, block.timestamp],
                                                            event_info.event.base_fee_l1, event_info.event.sender,
                                                            event_info.event.message_data_hash, overrides or {})

    async def send_l2_signed_tx(self, signed_tx: str, l2_deployer):
        delayed_inbox = load_contract(provider=self.l1_provider, contract_name='IInbox', address=self.l2_network.eth_bridge.inbox, is_classic=False)
        print('signed_tx', signed_tx)

        # print(signed_tx.rawTransaction)
        # Convert hex string to bytes
        # signed_tx_bytes = Web3.to_bytes(hexstr=signed_tx.rawTransaction)
        signed_tx_bytes = signed_tx.rawTransaction

        # InboxMessageKind.L2MessageType_signedTx as an integer
        message_type = InboxMessageKind.L2MessageType_signedTx.value

        # Pack the uint8 integer
        packed_message_type = struct.pack("B", message_type)  # 'B' is the format code for uint8

        # Concatenate the packed uint8 with the signed transaction bytes
        send_data_bytes = packed_message_type + signed_tx_bytes

        # Convert result to hex string if needed
        # send_data_hex = Web3.to_hex(send_data_bytes)

        transaction = delayed_inbox.functions.sendL2Message(send_data_bytes).transact({
        'from': self.l1_signer.account.address,
        })

        tx_receipt = self.l1_provider.eth.wait_for_transaction_receipt(transaction)        
        return tx_receipt
        


    async def sign_l2_tx(self, tx_request, l2_signer: SignerProviderUtils) -> str:
        tx = {**tx_request}
        contract_creation = self.is_contract_creation(tx)
        print("****", contract_creation)
        if 'nonce' not in tx:
            tx['nonce'] = l2_signer.provider.eth.get_transaction_count(l2_signer.account.address)

        if tx.get('type') == 1 or 'gasPrice' in tx:
            if 'gasPrice' in tx:
                tx['gasPrice'] = l2_signer.provider.eth.gas_price
        else:
            # Check if maxFeePerGas is not set in the transaction
            if 'maxFeePerGas' not in tx or tx['maxFeePerGas'] is None:
                # Fetch the current fee data from the network
                fee_data = l2_signer.provider.eth.fee_history(1, 'latest', reward_percentiles=[])

                # Set maxPriorityFeePerGas and maxFeePerGas
                # Note: 'maxPriorityFeePerGas' might need a default value if not provided by fee_data
                base_fee = fee_data['baseFeePerGas'][0]  # Base fee of the latest block
                priority_fee = Web3.to_wei(2, 'gwei')     # A default priority fee, adjust as needed

                tx['maxPriorityFeePerGas'] = priority_fee
                tx['maxFeePerGas'] = base_fee + priority_fee
            tx['type'] = 2

        tx['from'] = l2_signer.account.address
        tx['chainId'] = l2_signer.provider.eth.chain_id

        if 'to' not in tx:
            tx['to'] = Web3.to_checksum_address('0x0000000000000000000000000000000000000000')

        try:
            tx['gas'] = (await self.estimate_arbitrum_gas(tx, l2_signer.provider))["gasEstimateForL2"]
        except Exception:
            raise ArbSdkError('execution failed (estimate gas failed)')

        if contract_creation:
            del tx['to']
        print('tx', tx)
        return l2_signer.account.sign_transaction(tx)