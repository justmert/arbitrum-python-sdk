import struct
from typing import Optional, Dict, Any, List, Union

from eth_typing import BlockNumber, HexStr
from web3 import Web3
from web3.types import BlockData

from src.lib.data_entities.constants import ADDRESS_ZERO, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import InboxMessageKind
from src.lib.data_entities.networks import ArbitrumNetwork
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import (
    format_contract_output,
    load_contract,
    is_arbitrum_chain,
    is_defined,
    get_block_ranges_for_l1_block,
)
from src.lib.utils.multicall import MultiCaller
from src.lib.utils.arb_provider import ArbitrumProvider


class InboxTools:
    """
    Tools for interacting with the Inbox and Bridge contracts on Arbitrum networks.
    Similar to the TypeScript 'InboxTools' class, 
    includes methods for forced inclusion of delayed messages, 
    sending child-signed transactions, etc.
    """

    def __init__(self, parent_signer, child_chain: ArbitrumNetwork):
        """
        :param parent_signer: A Python 'signer' object that includes 'account' & 'provider'
        :param child_chain: The ArbitrumNetwork object describing L2 chain config
        """
        self.parent_signer = parent_signer
        self.parent_provider = SignerProviderUtils.get_provider(parent_signer)
        if not self.parent_provider:
            raise ArbSdkError("InboxTools requires a signer with a provider.")
        self.child_chain = child_chain

    async def find_first_block_below(self, block_number: int, block_timestamp: int):
        """
        Finds a block whose 'timestamp' is below a given timestamp, 
        starting from 'block_number' and working backwards if needed.

        :param block_number: A starting block number
        :param block_timestamp: The target timestamp 
        :return: The block (dict) if found
        :raises: On failure to find a suitable block
        """
        # If the parent chain is itself an Arbitrum chain, we may need to do extra logic
        is_parent_chain_arbitrum = await is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            # Attempt to use nodeInterface.l2BlockRangeForL1
            node_interface = load_contract(
                provider=self.parent_provider,
                contract_name="NodeInterface",
                address=NODE_INTERFACE_ADDRESS,
                is_classic=False,
            )

            try:
                # l2BlockRangeForL1 returns a struct { firstBlock, lastBlock }
                block_range_struct = node_interface.functions.l2BlockRangeForL1(block_number - 1).call()
                block_number = block_range_struct["firstBlock"]
            except Exception as e:
                # If that fails, do a fallback approach searching for L2 block near the L1 block
                block_ranges = await get_block_ranges_for_l1_block(
                    arbitrum_provider=self.parent_provider,
                    for_l1_block=block_number - 1,
                    allow_greater=True,
                )
                if not block_ranges:
                    raise e
                block_number = block_ranges[0]

        # get_block call - we assume parent_provider can do 'eth_getBlockByNumber'
        block: BlockData = self.parent_provider.eth.get_block(block_number)
        diff = block.timestamp - block_timestamp
        if diff < 0:
            return block

        # If the block's timestamp is still too high, step backwards
        average_block_time = 12
        diff_blocks = max(int(diff // average_block_time), 10)
        return await self.find_first_block_below(block_number - diff_blocks, block_timestamp)

    def is_contract_creation(self, child_transaction_request: Dict[str, Any]) -> bool:
        """
        Check if the transaction is a contract creation (i.e. no 'to' address or zero address).
        """
        to_addr = child_transaction_request.get("to")
        return (to_addr == "0x" or not to_addr or to_addr == ADDRESS_ZERO)

    async def estimate_arbitrum_gas(self, child_tx_request: Dict[str, Any], child_provider: Web3):
        """
        Estimate the gas usage for a child transaction using 
        nodeInterface.gasEstimateComponents (Arbitrum's method).

        :param child_tx_request: Minimal fields like 'to', 'data', 'from', 'value', etc.
        :param child_provider: A Web3 object connected to the child chain
        :return: A dict with the fields from gasEstimateComponents plus 'gasEstimateForChild'
        """
        node_interface = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            is_classic=False,
        )
        contract_creation = self.is_contract_creation(child_tx_request)

        # nodeInterface.gasEstimateComponents(
        #   address destAddr,
        #   bool isContractCreation,
        #   bytes calldata calldataForL2,
        # ) payable returns (gasEstimate, gasEstimateForL1, baseFee, l1BaseFeeEstimate)
        tx_params = {
            "from": child_tx_request["from"],
            "value": child_tx_request.get("value", 0),
        }

        result = node_interface.functions.gasEstimateComponents(
            child_tx_request.get("to", ADDRESS_ZERO),
            contract_creation,
            child_tx_request["data"]
        ).call(tx_params)

        # Format the output
        formatted = format_contract_output(node_interface, "gasEstimateComponents", result)
        gas_estimate_for_child = formatted["gasEstimate"] - formatted["gasEstimateForL1"]
        return {**formatted, "gasEstimateForChild": gas_estimate_for_child}

    async def get_force_includable_block_range(self, block_number_range_size: int) -> Dict[str, int]:
        """
        Determine a block range in which delayed messages have become eligible for forced inclusion.
        Uses SequencerInbox.maxTimeVariation() and the current block to figure out a range.

        :param block_number_range_size: The number of blocks to look backward from the 'first eligible block'
        :return: A dict { 'endBlock': <int>, 'startBlock': <int> } 
        """
        # Possibly the L1 block number if the parent chain is itself Arbitrum
        current_l1_block_number: Optional[int] = None

        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )

        is_parent_chain_arbitrum = await is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            # Use ArbitrumProvider to fetch the 'latest' block on the parent side
            arb_provider = ArbitrumProvider(self.parent_provider)
            current_arb_block = await arb_provider.get_block("latest")
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

        [max_time_variation, current_block_number, current_block_timestamp] = await multicall.multi_call(multicall_input, True)

        # If parent is Arbitrum, we use current_l1_block_number, else we use the actual block number
        block_number = current_l1_block_number if is_parent_chain_arbitrum else current_block_number

        # 'delayBlocks' / 'delaySeconds' from the contract
        first_eligible_block_number = block_number - max_time_variation["delayBlocks"]
        first_eligible_timestamp = current_block_timestamp - max_time_variation["delaySeconds"]

        first_eligible_block = await self.find_first_block_below(first_eligible_block_number, first_eligible_timestamp)
        return {
            "endBlock": first_eligible_block.number,
            "startBlock": first_eligible_block.number - block_number_range_size,
        }

    async def get_events_and_increase_range(
        self,
        bridge_contract,
        search_range_blocks: int,
        max_search_range_blocks: int,
        range_multiplier: int
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetches 'MessageDelivered' events from the bridge contract within a certain block range,
        expanding the search range if none are found until it hits maxSearchRangeBlocks.

        :param bridge_contract: Loaded contract for the Bridge
        :param search_range_blocks: Current search range size
        :param max_search_range_blocks: Maximum allowed range
        :param range_multiplier: Factor to multiply by each iteration
        :return: List of events found (or empty if none)
        """
        event_fetcher = EventFetcher(self.parent_provider)
        capped_search_range = min(search_range_blocks, max_search_range_blocks)
        block_range = await self.get_force_includable_block_range(capped_search_range)

        argument_filters = {}
        events = await event_fetcher.get_events(
            contract_factory=bridge_contract,
            event_name="MessageDelivered",
            argument_filters=argument_filters,
            filter={
                "fromBlock": block_range["startBlock"],
                "toBlock": block_range["endBlock"],
                "address": bridge_contract.address,
            },
        )

        if events:
            return events
        if capped_search_range == max_search_range_blocks:
            return []
        return await self.get_events_and_increase_range(
            bridge_contract,
            search_range_blocks * range_multiplier,
            max_search_range_blocks,
            range_multiplier
        )

    async def get_force_includable_event(
        self,
        max_search_range_blocks: int = 3 * 6545,
        start_search_range_blocks: int = 100,
        range_multiplier: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the 'latest' message that can be forcibly included on L1.

        :param max_search_range_blocks: Max blocks to look back (defaults ~3 days)
        :param start_search_range_blocks: Starting block range to search
        :param range_multiplier: Factor to multiply search range each iteration
        :return: A dict containing info about the event + 'delayedAcc', or None if none found
        """
        bridge_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Bridge",
            address=self.child_chain.eth_bridge.bridge,
            is_classic=False,
        )

        events = await self.get_events_and_increase_range(
            bridge_contract,
            start_search_range_blocks,
            max_search_range_blocks,
            range_multiplier
        )
        if not events:
            return None

        # The last event is the 'latest' message
        event_info = events[-1]

        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )
        total_delayed_read = await sequencer_inbox.functions.totalDelayedMessagesRead().call()
        if total_delayed_read > event_info["event"]["messageIndex"]:
            # Already read, no force inclusion needed
            return None

        delayed_acc = await bridge_contract.functions.delayedInboxAccs(
            event_info["event"]["messageIndex"]
        ).call()

        return {**event_info, "delayedAcc": delayed_acc}

    async def force_include(self, message_delivered_event: Optional[Dict[str, Any]] = None, overrides: Optional[Dict[str, Any]] = None):
        """
        Force-includes all eligible delayed messages up to and including the provided one.
        If no event is provided, we find the 'latest' includable event.

        :param message_delivered_event: An event object from get_force_includable_event() 
                                        that is known to be eligible.
        :param overrides: Transaction overrides dict for 'from', 'gas', etc.
        :return: Transaction receipt if success, or None if no event is eligible
        """
        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.eth_bridge.sequencer_inbox,
            is_classic=False,
        )

        event_info = message_delivered_event or await self.get_force_includable_event()
        if not event_info:
            return None

        block = self.parent_provider.eth.get_block(event_info["blockHash"])
        if overrides is None:
            overrides = {}
        if "from" not in overrides:
            overrides["from"] = self.parent_signer.account.address

        # sequencerInbox.forceInclusion(...)
        tx_hash = sequencer_inbox.functions.forceInclusion(
            event_info["event"]["messageIndex"] + 1,
            event_info["event"]["kind"],
            [event_info["blockNumber"], block.timestamp],
            event_info["event"]["baseFeeL1"],
            event_info["event"]["sender"],
            event_info["event"]["messageDataHash"],
        ).transact(overrides)

        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    async def send_child_signed_tx(self, signed_tx: Union[str, bytes]):
        """
        Send a child-chain-signed transaction via the delayed inbox on L1. 
        The childChain user signs the transaction for L2 execution, 
        and we embed it in an L1 transaction that is eventually replayed on L2.
        
        :param signed_tx: The child's transaction raw signature data (hex or bytes).
        :return: Transaction receipt on L1 for sending the message
        """
        delayed_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="IInbox",
            address=self.child_chain.eth_bridge.inbox,
            is_classic=False,
        )

        if isinstance(signed_tx, str):
            signed_tx_bytes = bytes.fromhex(signed_tx.replace("0x", ""))
        else:
            signed_tx_bytes = signed_tx

        message_type = InboxMessageKind.L2MessageType_signedTx.value
        # pack: one byte for kind, then the raw signedTx
        packed_message_type = struct.pack("B", message_type)
        send_data_bytes = packed_message_type + signed_tx_bytes

        tx = {
            "from": self.parent_signer.account.address,
        }

        tx_hash = delayed_inbox.functions.sendL2Message(send_data_bytes).transact(tx)
        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    async def sign_child_tx(self, tx_request: Dict[str, Any], child_signer) -> bytes:
        """
        Sign a transaction for the child chain (L2). 
        Typically, we then embed this signed Tx in the L1 delayed inbox message 
        via send_child_signed_tx(...).

        :param tx_request: A dict with fields like 'to', 'data', 'value', 'nonce', optional 'gasPrice' or EIP-1559 fields
        :param child_signer: The child's local signer object with an account & provider (connected to L2)
        :return: Raw signed transaction bytes
        :raises ArbSdkError: If gas estimation fails
        """
        # clone the request
        tx = dict(tx_request)
        contract_creation = self.is_contract_creation(tx)

        # If no nonce provided, fetch from chain
        if not is_defined(tx.get("nonce")):
            tx["nonce"] = child_signer.provider.eth.get_transaction_count(child_signer.account.address)

        # Check type & gas settings
        if tx.get("type") == 1 or "gasPrice" in tx:
            # we treat it as legacy or EIP-155
            if "gasPrice" in tx:
                tx["gasPrice"] = child_signer.provider.eth.gas_price
        else:
            # EIP-1559
            if not is_defined(tx.get("maxFeePerGas")):
                fee_history = child_signer.provider.eth.fee_history(1, "latest", reward_percentiles=[])
                base_fee = fee_history["baseFeePerGas"][0]
                priority_fee = Web3.to_wei(2, "gwei")
                tx["maxPriorityFeePerGas"] = priority_fee
                tx["maxFeePerGas"] = base_fee + priority_fee
            tx["type"] = 2

        tx["from"] = child_signer.account.address
        tx["chainId"] = child_signer.provider.eth.chain_id

        # If it's contract creation, user might not pass 'to'. 
        # But we need 'to'=0x0 for gas estimation. We'll remove it after.
        if not is_defined(tx.get("to")):
            tx["to"] = ADDRESS_ZERO

        # Estimate gas on the child chain
        try:
            gas_estimated = await self.estimate_arbitrum_gas(tx, child_signer.provider)
            tx["gas"] = gas_estimated["gasEstimateForChild"]
        except Exception as e:
            raise ArbSdkError("execution failed (estimate gas failed)") from e

        # If truly contract creation, remove 'to'
        if contract_creation:
            del tx["to"]

        # sign_transaction expects typical raw fields: nonce, gas, gasPrice or EIP-1559, chainId, to, value, data
        # We'll assume child_signer.account is a local account that supports sign_transaction.
        signed_tx = child_signer.account.sign_transaction(tx)
        return signed_tx.rawTransaction
