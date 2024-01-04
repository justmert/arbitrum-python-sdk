from web3 import Web3
from web3.contract import Contract
from typing import Any, Dict, Tuple


from src.lib.utils.helper import load_contract
from src.lib.data_entities.networks import l1_networks
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.multi_call import MultiCaller
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.message import InboxMessageKind


class InboxTools:
    def __init__(self, l1_signer: Any, l2_network: Any):
        self.l1_provider = SignerProviderUtils.get_provider(l1_signer)
        self.l1_network = l1_networks[l2_network.partner_chain_id]
        if not self.l1_network:
            raise ArbSdkError(f"L1Network not found for chain id: {l2_network.partner_chain_id}.")

    async def find_first_block_below(self, block_number: int, block_timestamp: int) -> Any:
        block = await self.l1_provider.getBlock(block_number)
        diff = block.timestamp - block_timestamp
        if diff < 0:
            return block

        diff_blocks = max(int(diff / self.l1_network.block_time), 10)
        return await self.find_first_block_below(block_number - diff_blocks, block_timestamp)

    def is_contract_creation(self, transaction_l2_request: Any) -> bool:
        return (
            transaction_l2_request.to == '0x' or
            not transaction_l2_request.to or
            transaction_l2_request.to == Web3.toChecksumAddress('0x0000000000000000000000000000000000000000')
        )

    async def estimate_arbitrum_gas(self, transaction_l2_request, l2_provider) -> Dict[str, Any]:
        node_interface = load_contract(provider=l2_provider, contract_name='NodeInterface', contract_address=NODE_INTERFACE_ADDRESS)
        contract_creation = self.is_contract_creation(transaction_l2_request)
        gas_components = await node_interface.callStatic.gasEstimateComponents(
            transaction_l2_request.to or Web3.toChecksumAddress('0x0000000000000000000000000000000000000000'),
            contract_creation,
            transaction_l2_request.data,
            {
                'from': transaction_l2_request.from_address,
                'value': transaction_l2_request.value,
            }
        )
        gas_estimate_for_l2 = gas_components.gasEstimate - gas_components.gasEstimateForL1
        return {**gas_components, 'gasEstimateForL2': gas_estimate_for_l2}

    async def get_force_includable_block_range(self, block_number_range_size: int) -> Dict[str, int]:
        sequencer_inbox = load_contract(provider=self.l1_provider, contract_name='SequencerInbox', contract_address=self.l2_network.eth_bridge.sequencer_inbox)
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
        
        bridge = load_contract(provider=self.l1_provider, contract_name='Bridge', contract_address=self.l2_network.eth_bridge.bridge)

        events = await self.get_events_and_increase_range(bridge, start_search_range_blocks, max_search_range_blocks, range_multiplier)

        if not events:
            return None

        event_info = events[-1]
        
        sequencer_inbox = load_contract(provider=self.l1_provider, contract_name='SequencerInbox', contract_address=self.l2_network.eth_bridge.sequencer_inbox)

        total_delayed_read = await sequencer_inbox.totalDelayedMessagesRead()

        if total_delayed_read > event_info.event.message_index:
            return None

        delayed_acc = await bridge.delayedInboxAccs(event_info.event.message_index)
        return {**event_info, 'delayedAcc': delayed_acc}

    async def force_include(self, message_delivered_event = None, overrides = None):
        
        sequencer_inbox = load_contract(provider=self.l1_signer, contract_name='SequencerInbox', contract_address=self.l2_network.eth_bridge.sequencer_inbox)

        event_info = message_delivered_event or await self.get_force_includable_event()

        if not event_info:
            return None

        block = await self.l1_provider.getBlock(event_info.block_hash)
        return await sequencer_inbox.functions.forceInclusion(event_info.event.message_index + 1, event_info.event.kind,
                                                            [event_info.block_number, block.timestamp],
                                                            event_info.event.base_fee_l1, event_info.event.sender,
                                                            event_info.event.message_data_hash, overrides or {})

    async def send_l2_signed_tx(self, signed_tx: str):
        
        delayed_inbox = load_contract(provider=self.l1_signer, contract_name='IInbox', contract_address=self.l2_network.eth_bridge.inbox)

        send_data = Web3.solidityPack(['uint8', 'bytes'], [Web3.toHex(InboxMessageKind.L2MessageType_signedTx), signed_tx])
        return await delayed_inbox.functions.sendL2Message(send_data)

    async def sign_l2_tx(self, tx_request, l2_signer: Any) -> str:
        tx = {**tx_request}
        contract_creation = self.is_contract_creation(tx)

        if 'nonce' not in tx:
            tx['nonce'] = await l2_signer.getTransactionCount()

        if tx.get('type') == 1 or 'gasPrice' in tx:
            if 'gasPrice' in tx:
                tx['gasPrice'] = await l2_signer.getGasPrice()
        else:
            if 'maxFeePerGas' not in tx:
                fee_data = await l2_signer.getFeeData()
                tx['maxPriorityFeePerGas'] = fee_data.maxPriorityFeePerGas
                tx['maxFeePerGas'] = fee_data.maxFeePerGas
            tx['type'] = 2

        tx['from'] = await l2_signer.getAddress()
        tx['chainId'] = await l2_signer.getChainId()

        if 'to' not in tx:
            tx['to'] = Web3.toChecksumAddress('0x0000000000000000000000000000000000000000')

        try:
            tx['gasLimit'] = (await self.estimate_arbitrum_gas(tx, l2_signer.provider)).gasEstimateForL2
        except Exception:
            raise ArbSdkError('execution failed (estimate gas failed)')

        if contract_creation:
            del tx['to']

        return await l2_signer.signTransaction(tx)