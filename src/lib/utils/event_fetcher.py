from web3 import Web3
from web3.contract import Contract

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import CaseDict, load_contract


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

        elif isinstance(provider, ArbitrumProvider):
            provider = provider.provider

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

        event = getattr(contract.events, event_name, None)
        if not event:
            raise ValueError(f"Event {event_name} not found in contract")

        event_filter = event().create_filter(
            **filter,
            argument_filters=argument_filters,
        )
        logs = event_filter.get_all_entries()
        fetched_events = []
        for log in logs:
            fetched_events.append(
                FetchedEvent(
                    event=log.args,
                    name=log.event,
                    topic=log.topics[0] if log.get("topics", None) and log["topics"] else None,
                    block_number=log["blockNumber"],
                    block_hash=log["blockHash"],
                    transaction_hash=log["transactionHash"],
                    address=log["address"],
                    topics=log.get("topics", None),
                    data=log.get("data", None),
                )
            )
        return fetched_events
