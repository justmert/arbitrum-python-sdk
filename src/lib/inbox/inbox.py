import struct
from typing import Optional, Dict, Any

from eth_typing import BlockNumber
from web3 import Web3

from src.lib.data_entities.constants import ADDRESS_ZERO, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import InboxMessageKind
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import (
    format_contract_output,
    load_contract,
    is_arbitrum_chain,
)
from src.lib.utils.lib import is_defined, get_block_ranges_for_l1_block
from src.lib.utils.multi_call import MultiCaller
from src.lib.utils.arb_provider import ArbitrumProvider


class InboxTools:
    def __init__(self, parent_signer, child_chain):
        self.parent_signer = parent_signer
        self.parent_provider = SignerProviderUtils.get_provider(parent_signer)
        self.child_chain = child_chain

    async def find_first_block_below(self, block_number: int, block_timestamp: int):
        is_parent_chain_arbitrum = await is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            node_interface = load_contract(
                provider=self.parent_provider,
                contract_name="NodeInterface",
                address=NODE_INTERFACE_ADDRESS,
                is_classic=False,
            )

            try:
                block_number = node_interface.functions.l2BlockRangeForL1(
                    block_number - 1
                ).call()["firstBlock"]
            except Exception as e:
                # Try binary search for nearest block if l2BlockRangeForL1 fails
                block_ranges = await get_block_ranges_for_l1_block(
                    arbitrum_provider=self.parent_provider,
                    for_l1_block=block_number - 1,
                    allow_greater=True,
                )
                
                if not block_ranges:
                    raise e
                    
                block_number = block_ranges[0]

        block = await self.parent_provider.eth.get_block(block_number)
        diff = block.timestamp - block_timestamp
        if diff < 0:
            return block

        # Take 12s average block time, move at least 10 blocks
        diff_blocks = max(int(diff / 12), 10)
        return await self.find_first_block_below(block_number - diff_blocks, block_timestamp)

    def is_contract_creation(self, child_transaction_request: Dict[str, Any]) -> bool:
        return (
            child_transaction_request.get("to") == "0x"
            or not child_transaction_request.get("to")
            or child_transaction_request.get("to") == ADDRESS_ZERO
        )

    async def estimate_arbitrum_gas(self, child_tx_request: Dict[str, Any], child_provider):
        node_interface = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            is_classic=False,
        )

        contract_creation = self.is_contract_creation(child_tx_request)

        gas_components = node_interface.functions.gasEstimateComponents(
            child_tx_request.get("to", ADDRESS_ZERO),
            contract_creation,
            child_tx_request["data"],
        ).call(
            {
                "from": child_tx_request["from"],
                "value": child_tx_request["value"],
            }
        )

        gas_components = format_contract_output(node_interface, "gasEstimateComponents", gas_components)
        gas_estimate_for_child = gas_components["gasEstimate"] - gas_components["gasEstimateForL1"]
        return {**gas_components, "gasEstimateForChild": gas_estimate_for_child}

    async def get_force_includable_block_range(self, block_number_range_size: int):
        current_l1_block_number = None 

        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )

        is_parent_chain_arbitrum = await is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            arb_provider = ArbitrumProvider(self.parent_provider)
            current_arb_block = await arb_provider.get_block('latest')
            current_l1_block_number = current_arb_block.l1_block_number

        multicall = await MultiCaller.from_provider(self.parent_provider)
        multicall_input = [
            {
                "targetAddr": sequencer_inbox.address,
                "encoder": lambda: sequencer_inbox.encode_function_data("maxTimeVariation"),
                "decoder": lambda return_data: sequencer_inbox.decode_function_result("maxTimeVariation", return_data)[0],
            },
            multicall.get_block_number_input(),
            multicall.get_current_block_timestamp_input(),
        ]

        max_time_variation, current_block_number, current_block_timestamp = await multicall.multi_call(multicall_input, True)

        block_number = current_l1_block_number if is_parent_chain_arbitrum else current_block_number

        first_eligible_block_number = block_number - max_time_variation.delay_blocks
        first_eligible_timestamp = current_block_timestamp - max_time_variation.delay_seconds

        first_eligible_block = await self.find_first_block_below(
            first_eligible_block_number, 
            first_eligible_timestamp
        )

        return {
            "endBlock": first_eligible_block.number,
            "startBlock": first_eligible_block.number - block_number_range_size,
        }

    async def get_events_and_increase_range(
        self,
        bridge,
        search_range_blocks: int,
        max_search_range_blocks: int,
        range_multiplier: int
    ):
        event_fetcher = EventFetcher(self.parent_provider)

        capped_search_range_blocks = min(search_range_blocks, max_search_range_blocks)
        block_range = await self.get_force_includable_block_range(capped_search_range_blocks)

        argument_filters = {}

        events = await event_fetcher.get_events(
            contract_factory=bridge,
            event_name="MessageDelivered",
            argument_filters=argument_filters,
            filter={
                "fromBlock": block_range["startBlock"],
                "toBlock": block_range["endBlock"],
                "address": bridge.address,
            },
        )

        if events:
            return events
        elif capped_search_range_blocks == max_search_range_blocks:
            return []
        else:
            return await self.get_events_and_increase_range(
                bridge,
                search_range_blocks * range_multiplier,
                max_search_range_blocks,
                range_multiplier,
            )

    async def get_force_includable_event(
        self,
        max_search_range_blocks: int = 3 * 6545,
        start_search_range_blocks: int = 100,
        range_multiplier: int = 2,
    ):
        """Find the event of the latest message that can be force included"""
        bridge = load_contract(
            provider=self.parent_provider,
            contract_name="Bridge",
            address=self.child_chain.eth_bridge.bridge,
            is_classic=False,
        )

        events = await self.get_events_and_increase_range(
            bridge, start_search_range_blocks, max_search_range_blocks, range_multiplier
        )

        if not events:
            return None

        event_info = events[-1]

        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )

        total_delayed_read = await sequencer_inbox.functions.totalDelayedMessagesRead().call()

        if total_delayed_read > event_info["event"]["messageIndex"]:
            return None

        delayed_acc = await bridge.functions.delayedInboxAccs(
            event_info["event"]["messageIndex"]
        ).call()
        
        return {**event_info, "delayedAcc": delayed_acc}

    async def force_include(self, message_delivered_event=None, overrides=None):
        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )

        event_info = message_delivered_event or await self.get_force_includable_event()

        if not event_info:
            return None

        block = await self.parent_provider.eth.get_block(event_info["blockHash"])

        if overrides is None:
            overrides = {}

        if "from" not in overrides:
            overrides["from"] = self.parent_signer.account.address

        tx_hash = sequencer_inbox.functions.forceInclusion(
            event_info["event"]["messageIndex"] + 1,
            event_info["event"]["kind"],
            [event_info["blockNumber"], block.timestamp],
            event_info["event"]["baseFeeL1"],
            event_info["event"]["sender"],
            event_info["event"]["messageDataHash"],
        ).transact(overrides)
        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    async def send_child_signed_tx(self, signed_tx: str):
        """Send Child Chain signed tx using delayed inbox"""
        delayed_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="IInbox",
            address=self.child_chain.eth_bridge.inbox,
            is_classic=False,
        )

        signed_tx_bytes = signed_tx if isinstance(signed_tx, bytes) else bytes.fromhex(signed_tx.replace('0x', ''))
        message_type = InboxMessageKind.L2MessageType_signedTx.value
        
        packed_message_type = struct.pack("B", message_type)
        send_data_bytes = packed_message_type + signed_tx_bytes

        tx = {
            "from": self.parent_signer.account.address,
        }

        tx_hash = delayed_inbox.functions.sendL2Message(send_data_bytes).transact(tx)
        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    async def sign_child_tx(self, tx_request: Dict[str, Any], child_signer):
        """Sign a transaction for the child chain"""
        tx = {**tx_request}
        contract_creation = self.is_contract_creation(tx)

        if not is_defined(tx.get("nonce")):
            tx["nonce"] = child_signer.provider.eth.get_transaction_count(
                child_signer.account.address
            )

        if tx.get("type") == 1 or "gasPrice" in tx:
            if "gasPrice" in tx:
                tx["gasPrice"] = await child_signer.provider.eth.gas_price
        else:
            if not is_defined(tx.get("maxFeePerGas")):
                fee_history = child_signer.provider.eth.fee_history(
                    1, "latest", reward_percentiles=[]
                )
                base_fee = fee_history["baseFeePerGas"][0]
                priority_fee = Web3.to_wei(2, "gwei")

                tx["maxPriorityFeePerGas"] = priority_fee
                tx["maxFeePerGas"] = base_fee + priority_fee

            tx["type"] = 2

        tx["from"] = child_signer.account.address
        tx["chainId"] = child_signer.provider.eth.chain_id

        if not is_defined(tx.get("to")):
            tx["to"] = ADDRESS_ZERO

        try:
            tx["gas"] = (
                await self.estimate_arbitrum_gas(tx, child_signer.provider)
            )["gasEstimateForChild"]
        except Exception as e:
            raise ArbSdkError("execution failed (estimate gas failed)") from e

        if contract_creation:
            del tx["to"]

        return child_signer.account.sign_transaction(tx)
