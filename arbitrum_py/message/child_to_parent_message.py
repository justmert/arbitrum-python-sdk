from typing import Any, Dict, List, Optional, Union

from web3 import Web3
from web3.providers import BaseProvider
from web3.types import BlockIdentifier

import arbitrum_py.message.child_to_parent_message_classic as classic
import arbitrum_py.message.child_to_parent_message_nitro as nitro
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.message import ChildToParentMessageStatus
from arbitrum_py.data_entities.networks import (
    get_arbitrum_network,
    get_nitro_genesis_block,
)
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils


class ChildToParentMessage:
    """
    Base functionality for Child-to-Parent messages.

    This class provides the core functionality for handling messages sent from a child
    chain to its parent chain in the Arbitrum ecosystem. It supports both Classic and
    Nitro message formats.
    """

    @staticmethod
    def is_classic(event: Dict[str, Any]) -> bool:
        """
        Check if the event is from the Classic format.

        Args:
            event: Event data containing transaction information

        Returns:
            True if the event is in Classic format, False if Nitro
        """
        return "indexInBatch" in event

    @staticmethod
    def from_event(
        parent_signer_or_provider: Any,
        event: Dict[str, Any],
        parent_provider: Optional[BaseProvider] = None,
    ) -> Union["ChildToParentMessageReader", "ChildToParentMessageWriter"]:
        """
        Create a message reader or writer based on the provided signer or provider.

        Args:
            parent_signer_or_provider: Signer or provider for the parent chain
            event: Event data containing the Child-to-Parent message information
            parent_provider: Optional override provider for the parent chain

        Returns:
            ChildToParentMessageWriter if a signer is provided,
            ChildToParentMessageReader if a provider is provided
        """
        if SignerProviderUtils.is_signer(parent_signer_or_provider):
            return ChildToParentMessageWriter(parent_signer_or_provider, event, parent_provider)
        else:
            return ChildToParentMessageReader(parent_signer_or_provider, event)

    @staticmethod
    def get_child_to_parent_events(
        child_provider: Web3,
        filter: Dict[str, BlockIdentifier],
        position: Optional[int] = None,
        destination: Optional[str] = None,
        hash: Optional[str] = None,
        index_in_batch: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get event logs for Child-to-Parent transactions.

        This method retrieves events from both Classic and Nitro formats within
        the specified block range.

        Args:
            child_provider: Web3 provider for the child chain
            filter: Block range filter containing fromBlock and toBlock
            position: Position in batch (for Nitro) or batch number (for Classic)
            destination: Destination address to filter events
            hash: Transaction hash to filter events
            index_in_batch: Index in batch (Classic only)

        Returns:
            List of event logs matching the specified criteria

        Raises:
            ArbSdkError: If an unrecognized block tag is provided
        """
        child_chain = get_arbitrum_network(child_provider)
        child_nitro_genesis_block = get_nitro_genesis_block(child_chain)

        def in_classic_range(block_tag: BlockIdentifier, nitro_gen_block: int) -> BlockIdentifier:
            """Determine the block range for Classic format."""
            if isinstance(block_tag, str):
                if block_tag == "earliest":
                    return 0
                elif block_tag in ["latest", "pending"]:
                    return nitro_gen_block
                else:
                    raise ArbSdkError(f"Unrecognised block tag: {block_tag}")
            return min(block_tag, nitro_gen_block)

        def in_nitro_range(block_tag: BlockIdentifier, nitro_gen_block: int) -> BlockIdentifier:
            """Determine the block range for Nitro format."""
            if isinstance(block_tag, str):
                if block_tag == "earliest":
                    return nitro_gen_block
                elif block_tag in ["latest", "pending"]:
                    return block_tag
                else:
                    raise ArbSdkError(f"Unrecognised block tag: {block_tag}")
            return max(block_tag, nitro_gen_block)

        classic_filter = {
            "fromBlock": in_classic_range(filter["fromBlock"], child_nitro_genesis_block),
            "toBlock": in_classic_range(filter["toBlock"], child_nitro_genesis_block),
        }

        nitro_filter = {
            "fromBlock": in_nitro_range(filter["fromBlock"], child_nitro_genesis_block),
            "toBlock": in_nitro_range(filter["toBlock"], child_nitro_genesis_block),
        }

        results = []
        if classic_filter["fromBlock"] != classic_filter["toBlock"]:
            classic_events = classic.ChildToParentMessageClassic.get_child_to_parent_events(
                child_provider,
                classic_filter,
                position,
                destination,
                hash,
                index_in_batch,
            )
            results.extend(classic_events)

        if nitro_filter["fromBlock"] != nitro_filter["toBlock"]:
            nitro_events = nitro.ChildToParentMessageNitro.get_child_to_parent_events(
                child_provider, nitro_filter, position, destination, hash
            )
            results.extend(nitro_events)

        return results


class ChildToParentMessageReader(ChildToParentMessage):
    """
    Provides read-only access for Child-to-Parent messages.

    This class handles reading and querying the status of messages sent from
    a child chain to its parent chain.
    """

    def __init__(self, parent_provider: BaseProvider, event: Dict[str, Any]) -> None:
        """
        Initialize a read-only message handler.

        Args:
            parent_provider: Provider for the parent chain
            event: Event data containing the message information
        """
        super().__init__()
        if self.is_classic(event):
            self.classic_reader = classic.ChildToParentMessageReaderClassic(
                parent_provider, event["batchNumber"], event["indexInBatch"]
            )
            self.nitro_reader = None
        else:
            self.nitro_reader = nitro.ChildToParentMessageReaderNitro(parent_provider, event)
            self.classic_reader = None

    def get_outbox_proof(self, child_provider: Web3) -> Union[Dict[str, Any], List[str], None]:
        """
        Get the outbox proof for the message.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            Proof information for Classic format, merkle proof for Nitro format,
            or None if proof is not available
        """
        if self.nitro_reader:
            return self.nitro_reader.get_outbox_proof(child_provider)
        else:
            return self.classic_reader.get_outbox_proof(child_provider)

    def status(self, child_provider: Web3) -> ChildToParentMessageStatus:
        """
        Get the current status of the message.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            Current status of the Child-to-Parent message
        """
        if self.nitro_reader:
            return self.nitro_reader.status(child_provider)
        else:
            return self.classic_reader.status(child_provider)

    def wait_until_ready_to_execute(self, child_provider: Web3, retry_delay: int = 500) -> ChildToParentMessageStatus:
        """
        Wait until the message is ready to be executed.

        Warning:
            This operation may take a very long time (1 week+) as outbox entries
            are only created when the corresponding node is confirmed.

        Args:
            child_provider: Web3 provider for the child chain
            retry_delay: Milliseconds to wait between status checks

        Returns:
            Final message status (either EXECUTED or CONFIRMED)
        """
        if self.nitro_reader:
            return self.nitro_reader.wait_until_ready_to_execute(child_provider, retry_delay)
        else:
            return self.classic_reader.wait_until_ready_to_execute(child_provider, retry_delay)

    def get_first_executable_block(self, child_provider: Web3) -> Optional[int]:
        """
        Get the first block where this message can be executed.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            Block number where message becomes executable, or None if already
            executable or executed
        """
        if self.nitro_reader:
            return self.nitro_reader.get_first_executable_block(child_provider)
        else:
            return self.classic_reader.get_first_executable_block(child_provider)


class ChildToParentMessageWriter(ChildToParentMessageReader):
    """
    Provides read and write access for Child-to-Parent messages.

    This class extends ChildToParentMessageReader to add the ability to
    execute messages on the parent chain.
    """

    def __init__(
        self,
        parent_signer: Any,
        event: Dict[str, Any],
        parent_provider: Optional[BaseProvider] = None,
    ) -> None:
        """
        Initialize a message handler with write capabilities.

        Args:
            parent_signer: Signer for the parent chain
            event: Event data containing the message information
            parent_provider: Optional override provider for the parent chain
        """
        super().__init__(parent_provider or parent_signer.provider, event)
        if self.is_classic(event):
            self.classic_writer = classic.ChildToParentMessageWriterClassic(
                parent_signer, event["batchNumber"], event["indexInBatch"], parent_provider
            )
            self.nitro_writer = None
        else:
            self.nitro_writer = nitro.ChildToParentMessageWriterNitro(parent_signer, event, parent_provider)
            self.classic_writer = None

    def execute(self, child_provider: Web3, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the Child-to-Parent message on the parent chain.

        Args:
            child_provider: Web3 provider for the child chain
            overrides: Optional transaction parameter overrides

        Returns:
            Transaction receipt

        Raises:
            Exception: If the outbox entry has not been created
        """
        if self.nitro_writer:
            return self.nitro_writer.execute(child_provider, overrides)
        else:
            return self.classic_writer.execute(child_provider, overrides)
