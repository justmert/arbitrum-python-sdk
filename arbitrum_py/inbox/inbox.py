import struct
from typing import Any, Dict, List, Optional, Union

from web3 import Web3
from web3.types import BlockData

from arbitrum_py.data_entities.constants import ADDRESS_ZERO, NODE_INTERFACE_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.message import InboxMessageKind
from arbitrum_py.data_entities.networks import ArbitrumNetwork
from arbitrum_py.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from arbitrum_py.utils.event_fetcher import EventFetcher
from arbitrum_py.utils.helper import format_contract_output, load_contract
from arbitrum_py.utils.lib import (
    get_block_ranges_for_l1_block,
    is_arbitrum_chain,
    is_defined,
)
from arbitrum_py.utils.multicall import MultiCaller


class InboxTools:
    """
    Tools for interacting with the Inbox and Bridge contracts on Arbitrum networks.
    Similar to the TypeScript 'InboxTools' class,
    includes methods for forced inclusion of delayed messages,
    sending child-signed transactions, etc.
    """

    def __init__(self, parent_signer: SignerOrProvider, child_chain: ArbitrumNetwork) -> None:
        """
        :param parent_signer: A Python 'signer' object that includes 'account' & 'provider'
        :param child_chain: The ArbitrumNetwork object describing L2 chain config
        """
        self.parent_signer = SignerProviderUtils.get_signer(parent_signer)
        self.parent_provider = SignerProviderUtils.get_provider(parent_signer)
        if not self.parent_provider:
            raise ArbSdkError("InboxTools requires a signer with a provider.")
        self.child_chain = child_chain

    def find_first_block_below(self, block_number: int, block_timestamp: int):
        """
        Finds a block whose 'timestamp' is below a given timestamp,
        starting from 'block_number' and working backwards if needed.

        :param block_number: A starting block number
        :param block_timestamp: The target timestamp
        :return: The block (dict) if found
        :raises: On failure to find a suitable block
        """
        # If the parent chain is itself an Arbitrum chain, we may need to do extra logic
        is_parent_chain_arbitrum = is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            # Attempt to use nodeInterface.l2BlockRangeForL1
            node_interface = load_contract(
                provider=self.parent_provider,
                contract_name="NodeInterface",
                address=NODE_INTERFACE_ADDRESS,
            )

            try:
                # l2BlockRangeForL1 returns a struct { firstBlock, lastBlock }
                block_range_struct = node_interface.functions.l2BlockRangeForL1(block_number - 1).call()
                block_number = block_range_struct["firstBlock"]
            except Exception as e:
                # If that fails, do a fallback approach searching for L2 block near the L1 block
                block_ranges = get_block_ranges_for_l1_block(
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
        return self.find_first_block_below(block_number - diff_blocks, block_timestamp)

    def is_contract_creation(self, child_transaction_request: Dict[str, Any]) -> bool:
        """
        Check if the transaction is a contract creation (i.e. no 'to' address or zero address).
        """
        to_addr = child_transaction_request.get("to")
        return to_addr == "0x" or not to_addr or to_addr == ADDRESS_ZERO

    def estimate_arbitrum_gas(self, child_tx_request: Dict[str, Any], child_provider: Web3) -> Dict[str, Any]:
        """Estimate gas components for an Arbitrum transaction.

        We should use nodeInterface to get the gas estimate because we
        are making a delayed inbox message which doesn't need parent calldata
        gas fee part.

        Args:
            child_tx_request: Transaction parameters for the child chain
            child_provider: Web3 provider for the child chain

        Returns:
            Gas components including estimates for L1 and L2 portions

        Raises:
            ArbSdkError: If gas estimation fails
        """
        # Load NodeInterface contract
        node_interface = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
        )

        # Check if contract creation
        contract_creation = self.is_contract_creation(child_tx_request)

        # Prepare call parameters
        tx_params = {
            "from": child_tx_request["from"],
            "value": child_tx_request.get("value", 0),
        }

        # Call gasEstimateComponents
        result = node_interface.functions.gasEstimateComponents(
            child_tx_request.get("to") if child_tx_request.get("to") else ADDRESS_ZERO,
            contract_creation,
            child_tx_request.get("data", "0x"),
        ).call(tx_params)

        # Format the output
        formatted = format_contract_output(node_interface, "gasEstimateComponents", result)

        # Calculate child gas estimate
        gas_estimate_for_child = formatted["gasEstimate"] - formatted["gasEstimateForL1"]

        return {
            "gasEstimate": formatted["gasEstimate"],
            "gasEstimateForL1": formatted["gasEstimateForL1"],
            "baseFee": formatted["baseFee"],
            "l1BaseFeeEstimate": formatted["l1BaseFeeEstimate"],
            "gasEstimateForChild": gas_estimate_for_child,
        }

    def get_force_includable_block_range(self, block_number_range_size: int) -> Dict[str, int]:
        """Get block range where delayed messages can be force-included.

        Uses SequencerInbox.maxTimeVariation() to determine when messages
        become eligible for forced inclusion.

        Args:
            block_number_range_size: Number of blocks to look back from
                the first eligible block

        Returns:
            Dict containing fromBlock and toBlock numbers
        """
        # Track L1 block number if parent is Arbitrum
        current_l1_block_number = None

        # Load sequencer inbox contract
        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.ethBridge.sequencerInbox,
        )

        # Check if parent chain is Arbitrum
        is_parent_chain_arbitrum = is_arbitrum_chain(self.parent_provider)

        if is_parent_chain_arbitrum:
            # Use ArbitrumProvider to fetch the 'latest' block on the parent side
            arb_provider = self.parent_provider
            current_arb_block = arb_provider.eth.get_block("latest")
            current_l1_block_number = current_arb_block["l1BlockNumber"]

        # Setup multicall for batch requests
        multicall = MultiCaller.from_provider(self.parent_provider)
        multicall_input = [
            {
                "targetAddr": sequencer_inbox.address,
                "encoder": lambda: sequencer_inbox.encode_function_data("maxTimeVariation"),
                "decoder": lambda return_data: sequencer_inbox.decode_function_result("maxTimeVariation", return_data)[
                    0
                ],
            },
            multicall.get_block_number_input(),
            multicall.get_current_block_timestamp_input(),
        ]

        # Get max time variation and current block info
        [max_time_variation, current_block_number, current_block_timestamp] = multicall.multi_call(
            multicall_input, True
        )

        # If parent is Arbitrum, use L1 block number, else use actual block number
        block_number = current_l1_block_number if is_parent_chain_arbitrum else current_block_number

        # Calculate first eligible block based on delay parameters
        first_eligible_block_number = block_number - max_time_variation["delayBlocks"]
        first_eligible_timestamp = current_block_timestamp - max_time_variation["delaySeconds"]

        # Find first eligible block
        first_eligible_block = self.find_first_block_below(first_eligible_block_number, first_eligible_timestamp)

        return {
            "startBlock": first_eligible_block.number - block_number_range_size,
            "endBlock": first_eligible_block.number,
        }

    def get_events_and_increase_range(
        self,
        bridge_contract,
        search_range_blocks: int,
        max_search_range_blocks: int,
        range_multiplier: int,
    ) -> List[Dict[str, Any]]:
        """Recursively fetch MessageDelivered events.

        Look for force includable events in the search range blocks. If no events
        are found, the search range is increased incrementally up to the max
        search range blocks.

        Args:
            bridge_contract: Bridge contract instance
            search_range_blocks: Initial block range to search
            max_search_range_blocks: Maximum block range to search
            range_multiplier: Factor to multiply range by on each iteration

        Returns:
            List of MessageDelivered events found

        Raises:
            ArbSdkError: If no events found within max range
        """
        # Initialize event fetcher
        event_fetcher = EventFetcher(self.parent_provider)

        # Cap search range at maximum
        capped_search_range = min(search_range_blocks, max_search_range_blocks)

        # Get block range for search
        block_range = self.get_force_includable_block_range(capped_search_range)

        # Setup event filter
        argument_filters = {}
        events = event_fetcher.get_events(
            contract_factory=bridge_contract,
            event_name="MessageDelivered",
            argument_filters=argument_filters,
            filter={
                "fromBlock": block_range["startBlock"],
                "toBlock": block_range["endBlock"],
                "address": bridge_contract.address,
            },
        )

        # Return events if found
        if events:
            return events

        # If at max range and no events, return empty list
        if capped_search_range == max_search_range_blocks:
            return []

        # Otherwise increase range and try again
        return self.get_events_and_increase_range(
            bridge_contract,
            search_range_blocks * range_multiplier,
            max_search_range_blocks,
            range_multiplier,
        )

    def get_force_includable_event(
        self,
        max_search_range_blocks: int = 3 * 6545,
        start_search_range_blocks: int = 100,
        range_multiplier: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """Find the event of the latest message that can be force included.

        Args:
            max_search_range_blocks: Max blocks to look back (~3 days default)
            start_search_range_blocks: Initial block range to search
            range_multiplier: Factor to multiply range by on each iteration

        Returns:
            ForceInclusionParams if a forceable message is found, None otherwise
        """
        # Load bridge contract
        bridge_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Bridge",
            address=self.child_chain.ethBridge.bridge,
        )

        # Get events with increasing range if needed
        events = self.get_events_and_increase_range(
            bridge_contract,
            start_search_range_blocks,
            max_search_range_blocks,
            range_multiplier,
        )

        if not events:
            return None

        # Get latest event
        latest_event = events[-1]

        # Check if already read
        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.ethBridge.sequencerInbox,
        )
        total_delayed_read = sequencer_inbox.functions.totalDelayedMessagesRead().call()
        if total_delayed_read > latest_event["event"]["messageIndex"]:
            # Already read, no force inclusion needed
            return None

        # Get delayed accumulator
        delayed_acc = bridge_contract.functions.delayedInboxAccs(latest_event["event"]["messageIndex"]).call()

        return {**latest_event, "delayedAcc": delayed_acc}

    def force_include(
        self,
        message_delivered_event: Optional[Dict[str, Any]] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Force includes all eligible messages in the delayed inbox.

        The inbox contract doesn't allow a message to be force-included
        until after a delay period has been completed.

        Args:
            message_delivered_event: Event and accumulator from get_force_includable_event
            overrides: Optional transaction parameter overrides

        Returns:
            Transaction receipt if successful, None if no event to include

        Raises:
            ArbSdkError: If force inclusion fails
        """
        sequencer_inbox = load_contract(
            provider=self.parent_provider,
            contract_name="SequencerInbox",
            address=self.child_chain.ethBridge.sequencerInbox,
        )

        event_info = message_delivered_event or self.get_force_includable_event()
        if not event_info:
            return None

        block = self.parent_provider.eth.get_block(event_info["blockHash"])
        if overrides is None:
            overrides = {}
        if "from" not in overrides:
            overrides["from"] = self.parent_signer.address

        # sequencerInbox.forceInclusion(...)
        tx = sequencer_inbox.functions.forceInclusion(
            event_info["event"]["messageIndex"] + 1,
            event_info["event"]["kind"],
            [event_info["blockNumber"], block.timestamp],
            event_info["event"]["baseFeeL1"],
            event_info["event"]["sender"],
            event_info["event"]["messageDataHash"],
        ).build_transaction(overrides)

        signed_tx = self.parent_signer.sign_transaction(tx)
        tx_hash = self.parent_provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    def send_child_signed_tx(self, signed_tx: Union[str, bytes]) -> Dict[str, Any]:
        """Send a child-chain-signed transaction via the delayed inbox on L1.

        The childChain user signs the transaction for L2 execution,
        and we embed it in an L1 transaction that is eventually replayed on L2.
        If it isn't included within 24 hours, you can force include it.

        Args:
            signed_tx: The child's transaction raw signature data (hex or bytes)

        Returns:
            Transaction receipt on L1 for sending the message

        Example:
            >>> # Sign and send L2 transaction via L1
            >>> tx = {'to': '0x1234...', 'value': 1000000000000000000}
            >>> signed = inbox_tools.sign_child_tx(tx, l2_signer)
            >>> receipt = inbox_tools.send_child_signed_tx(signed)
        """
        # Load inbox contract
        inbox = load_contract(
            provider=self.parent_provider,
            contract_name="IInbox",
            address=self.child_chain.ethBridge.inbox,
        )

        # Convert hex string to bytes if needed
        if isinstance(signed_tx, str):
            signed_tx_bytes = bytes.fromhex(signed_tx.replace("0x", ""))
        else:
            signed_tx_bytes = signed_tx

        # Pack message type with signed tx
        message_type = InboxMessageKind.L2MessageType_signedTx.value
        packed_message_type = struct.pack("B", message_type)
        send_data_bytes = packed_message_type + signed_tx_bytes

        # Build transaction
        tx = inbox.functions.sendL2Message(send_data_bytes).build_transaction(
            {
                "from": self.parent_signer.address,
                "nonce": self.parent_provider.eth.get_transaction_count(self.parent_signer.address),
            }
        )

        # Sign and send transaction
        signed_tx = self.parent_signer.sign_transaction(tx)
        tx_hash = self.parent_provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        return self.parent_provider.eth.wait_for_transaction_receipt(tx_hash)

    def sign_child_tx(self, tx_request: Dict[str, Any], child_signer: SignerOrProvider) -> bytes:
        """Sign a transaction for the child chain (L2).

        Typically, we then embed this signed Tx in the L1 delayed inbox message
        via send_child_signed_tx(...).

        Args:
            tx_request: A dict with fields like 'to', 'data', 'value', 'nonce',
                optional 'gasPrice' or EIP-1559 fields
            child_signer: The child's local signer object with an account &
                provider (connected to L2)

        Returns:
            Raw signed transaction bytes

        Raises:
            ArbSdkError: If gas estimation fails
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
            gas_estimated = self.estimate_arbitrum_gas(tx, child_signer.provider)
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
