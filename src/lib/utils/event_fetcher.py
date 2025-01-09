from typing import List, Optional, Union

from web3 import Web3
from web3.contract import Contract

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import CaseDict, load_contract


class FetchedEvent(CaseDict):
    """
    Python equivalent of the TypeScript `FetchedEvent<TEvent>`.
    Stores the parsed event fields such as name, blockNumber, transactionHash, etc.
    """

    def __init__(
        self,
        *,
        event: dict,
        topic: Optional[str],
        name: str,
        block_number: int,
        block_hash: str,
        transaction_hash: str,
        address: str,
        topics: List[str],
        data: Optional[str],
    ):
        """
        :param event: The parsed event.args object
        :param topic: The primary topic used in the log
        :param name: The name of the event (e.g. "MessageDelivered")
        :param block_number: The block number where the log was found
        :param block_hash: The block hash
        :param transaction_hash: The transaction hash containing this log
        :param address: The contract address that emitted this log
        :param topics: The raw topics from the log
        :param data: The raw data from the log
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
    A utility class for fetching logs and parsing them into structured events.
    This is analogous to the TypeScript `EventFetcher` class.
    """

    def __init__(self, provider: Union[Web3, SignerOrProvider, ArbitrumProvider]):
        """
        :param provider: A raw Web3 instance, a SignerOrProvider, or an ArbitrumProvider
                         from which to fetch logs.
        """
        if isinstance(provider, Web3):
            self.provider = provider
        elif isinstance(provider, SignerOrProvider):
            if provider.provider is None:
                raise ArbSdkError("Invalid SignerOrProvider - no .provider found")
            self.provider = provider.provider
        elif isinstance(provider, ArbitrumProvider):
            # unwrap the provider
            self.provider = provider.provider
        else:
            raise ArbSdkError("Invalid provider type for EventFetcher")

    def get_events(
        self,
        contract_factory: Union[str, Contract],
        event_name: str,
        argument_filters: Optional[dict] = None,
        filter: Optional[dict] = None,
        is_classic: bool = False,
    ) -> List[FetchedEvent]:
        """
        Fetch logs from the chain using the given contract and event name,
        and parse them into FetchedEvent objects.

        :param contract_factory: Either a string contract name or an actual Contract instance
        :param event_name: The name of the event (e.g. 'MessageDelivered')
        :param argument_filters: Additional argument filters for the event
        :param filter: A dict with 'fromBlock', 'toBlock', 'address', etc.
        :param is_classic: Whether to load the 'classic' or 'nitro' version of the contract
        :return: A list of FetchedEvent objects describing each log
        """
        if filter is None:
            filter = {}
        if argument_filters is None:
            argument_filters = {}

        # 1) Build or retrieve the contract instance
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
            raise ArbSdkError("Invalid contract factory type - must be name or Contract instance")

        # 2) Attempt to retrieve the event by name
        event_abi = getattr(contract.events, event_name, None)
        if not event_abi:
            raise ArbSdkError(f"Event {event_name} not found in contract's ABI")

        # 3) Create a filter for the event
        #    E.g. fromBlock=..., toBlock=..., argument_filters=...
        event_filter = event_abi().create_filter(argument_filters=argument_filters, **filter)

        # 4) Grab all matching logs
        logs = event_filter.get_all_entries()
        fetched_events: List[FetchedEvent] = []

        for log in logs:
            # build a FetchedEvent
            top_topic = log["topics"][0] if "topics" in log and log["topics"] else None
            ev = FetchedEvent(
                event=dict(log.args),
                topic=top_topic,
                name=log.event,
                block_number=log["blockNumber"],
                block_hash=log["blockHash"],
                transaction_hash=log["transactionHash"],
                address=log["address"],
                topics=log.get("topics", []),
                data=log.get("data"),
            )
            fetched_events.append(ev)

        return fetched_events
