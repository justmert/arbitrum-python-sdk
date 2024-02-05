from web3 import Web3
from src.lib.data_entities.errors import ArbSdkError

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import load_contract
from web3.contract import Contract

from test import CaseDict


class FetchedEvent(CaseDict):
    def __init__(
        self,
        event,
        topic,
        name,
        block_number,
        block_hash,
        transaction_hash,
        address,
        topics,
        data,
    ):
        self.event = event
        self.topic = topic
        self.name = name
        self.block_number = block_number
        self.block_hash = block_hash
        self.transaction_hash = transaction_hash
        self.address = address
        self.topics = topics
        self.data = data

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


class EventFetcher:
    def __init__(self, provider):
        if isinstance(provider, Web3):
            self.provider = provider

        elif isinstance(provider, SignerOrProvider):
            self.provider = provider.provider

        else:
            raise Exception("Invalid provider type")

    async def get_events(
        self,
        contract_factory,
        event_name,
        argument_filters=None,
        filter=None,
        is_classic=False,
    ):
        if filter is None:
            filter = {}

        if argument_filters is None:
            argument_filters = {}

        if isinstance(contract_factory, str):
            contract_address = filter.get(
                "address",
                Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
            )

            contract = load_contract(
                provider=self.provider,
                contract_name=contract_factory,
                address=contract_address,
                is_classic=is_classic,
            )

        elif isinstance(contract_factory, Contract):
            contract = contract_factory
        else:
            raise ArbSdkError("Invalid contract factory type")

        events = (
            getattr(contract.events, event_name)
            .create_filter(
                toBlock=filter["toBlock"],
                fromBlock=filter["fromBlock"],
                address=filter["address"],
                argument_filters=argument_filters,
            )
            .get_all_entries()
        )

        return _format_events(events)


def _format_events(self, events):
    fetched_events = []
    for event in events:
        fetched_event = FetchedEvent(
            event=event["args"],
            topic=event.get("topics", None),
            name=event.event,
            block_number=event.blockNumber,
            block_hash=event.blockHash.hex(),
            transaction_hash=event.transactionHash.hex(),
            address=event.address,
            topics=[topic.hex() for topic in event["topics"]],
            data=event["data"],
        )
        fetched_events.append(fetched_event)

    return fetched_events
