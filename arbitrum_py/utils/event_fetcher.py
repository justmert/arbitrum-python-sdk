"""
Event fetching and parsing utilities for the Arbitrum SDK.

This module provides classes for fetching and parsing blockchain events/logs
in a structured way, similar to the TypeScript EventFetcher implementation.
"""

from typing import Any, Dict, List, Optional, TypeVar, Union

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.types import FilterParams

from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider
from arbitrum_py.utils.arb_provider import ArbitrumProvider
from arbitrum_py.utils.helper import CaseDict, load_contract

T = TypeVar("T")  # For generic type hints


class FetchedEvent(CaseDict):
    """
    A structured representation of an Ethereum event/log.

    This class represents a parsed blockchain event, containing both the decoded
    data (event arguments) and the raw log information. It's the Python equivalent
    of the TypeScript FetchedEvent<TEvent> type.

    Attributes:
        event (Dict[str, Any]): The decoded event arguments
        topic (Optional[str]): The primary topic (event signature)
        name (str): The event name (e.g., "MessageDelivered")
        block_number (int): Block number containing the event
        block_hash (str): Hash of the block containing the event
        transaction_hash (str): Hash of the transaction containing the event
        address (str): Contract address that emitted the event
        topics (List[str]): All topics from the log
        data (Optional[str]): Raw data from the log
    """

    def __init__(
        self,
        *,
        event: Dict[str, Any],
        topic: Optional[str],
        name: str,
        block_number: int,
        block_hash: str,
        transaction_hash: str,
        address: ChecksumAddress,
        topics: List[str],
        data: Optional[str],
    ) -> None:
        """
        Initialize a FetchedEvent instance.

        Args:
            event: The decoded event arguments
            topic: Primary topic (event signature) if any
            name: Event name (e.g., "MessageDelivered")
            block_number: Block number containing the event
            block_hash: Hash of the block containing the event
            transaction_hash: Hash of the transaction containing the event
            address: Contract address that emitted the event
            topics: All topics from the log
            data: Raw data from the log
        """
        super().__init__(
            {
                "event": event,
                "topic": topic,
                "name": name,
                "blockNumber": block_number,
                "blockHash": block_hash,
                "transactionHash": transaction_hash,
                "address": address,
                "topics": topics,
                "data": data,
            }
        )
        self.event = event
        self.topic = topic
        self.name = name
        self.block_number = block_number
        self.block_hash = block_hash
        self.transaction_hash = transaction_hash
        self.address = address
        self.topics = topics
        self.data = data


class EventFetcher:
    """
    A utility class for fetching and parsing blockchain events.

    This class provides functionality to:
    1. Query blockchain logs using various filters
    2. Parse the logs into structured FetchedEvent objects
    3. Handle different provider types (Web3, SignerOrProvider, ArbitrumProvider)

    It's the Python equivalent of the TypeScript EventFetcher class.
    """

    def __init__(self, provider: Union[Web3, SignerOrProvider, ArbitrumProvider]) -> None:
        """
        Initialize an EventFetcher instance.

        Args:
            provider: The provider to use for fetching logs. Can be:
                     - A Web3 instance
                     - A SignerOrProvider instance
                     - An ArbitrumProvider instance

        Raises:
            ArbSdkError: If the provider is invalid or missing
        """
        if isinstance(provider, Web3):
            self.provider = provider
        elif isinstance(provider, SignerOrProvider):
            if provider.provider is None:
                raise ArbSdkError("Invalid SignerOrProvider - no .provider found")
            self.provider = provider.provider
        elif isinstance(provider, ArbitrumProvider):
            self.provider = provider.provider
        else:
            raise ArbSdkError(f"Invalid provider type for EventFetcher: {type(provider)}")

    def get_events(
        self,
        contract_factory: Union[str, Contract],
        event_name: str,
        argument_filters: Optional[Dict[str, Any]] = None,
        filter: Optional[FilterParams] = None,
        is_classic: bool = False,
    ) -> List[FetchedEvent]:
        """
        Fetch and parse blockchain events.

        This method:
        1. Sets up the contract interface
        2. Creates an event filter
        3. Fetches matching logs
        4. Parses them into FetchedEvent objects

        Args:
            contract_factory: Either a contract name string or Contract instance
            event_name: Name of the event to fetch (e.g., 'MessageDelivered')
            argument_filters: Filters for specific event argument values
            filter: Block range and address filters containing:
                   - fromBlock: Starting block number
                   - toBlock: Ending block number
                   - address: Contract address (optional)
            is_classic: Whether to use classic or nitro contract version

        Returns:
            List[FetchedEvent]: The fetched and parsed events

        Raises:
            ArbSdkError: If contract or event cannot be found/accessed

        Example:
            >>> fetcher = EventFetcher(web3)
            >>> events = fetcher.get_events(
            ...     contract_factory='Bridge',
            ...     event_name='MessageDelivered',
            ...     filter={'fromBlock': 1000000, 'toBlock': 'latest'}
            ... )
        """
        filter = filter or {}
        argument_filters = argument_filters or {}

        # 1. Build or retrieve the contract instance
        if isinstance(contract_factory, str):
            contract_address = filter.get(
                "address", Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
            )
            contract = load_contract(
                provider=self.provider,
                contract_name=contract_factory,
                address=contract_address,
            )
        elif isinstance(contract_factory, Contract):
            contract = contract_factory
        else:
            raise ArbSdkError(
                f"Invalid contract_factory type: {type(contract_factory)}. " "Must be string name or Contract instance"
            )

        # 2. Get the event object
        event_abi = getattr(contract.events, event_name, None)
        if not event_abi:
            raise ArbSdkError(
                f"Event '{event_name}' not found in contract ABI. "
                f"Available events: {', '.join(contract.events.__dict__.keys())}"
            )

        # 3. Create and execute the event filter
        try:
            event_filter = event_abi().create_filter(argument_filters=argument_filters, **filter)
            logs = event_filter.get_all_entries()
        except Exception as e:
            raise ArbSdkError(f"Failed to fetch events: {str(e)}") from e

        # 4. Parse logs into FetchedEvent objects
        fetched_events: List[FetchedEvent] = []
        for log in logs:
            try:
                # Safely extract the first topic if available
                topics = log.get("topics", [])
                top_topic = topics[0].hex() if topics else None

                # Convert log to FetchedEvent
                ev = FetchedEvent(
                    event=dict(log.args),
                    topic=top_topic,
                    name=log.event,
                    block_number=log["blockNumber"],
                    block_hash=log["blockHash"].hex(),
                    transaction_hash=log["transactionHash"].hex(),
                    address=log["address"],
                    topics=[t.hex() if isinstance(t, bytes) else t for t in topics],
                    data=log.get("data"),
                )
                fetched_events.append(ev)
            except Exception as e:
                # Log error but continue processing other events

                continue

        return fetched_events
