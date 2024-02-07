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

        event = getattr(contract.events, event_name, None)
        if not event:
            raise ValueError(f"Event {event_name} not found in contract")

        event_filter = event().create_filter(
            toBlock=filter["toBlock"],
            fromBlock=filter["fromBlock"],
            address=filter["address"],
            argument_filters=argument_filters
        )
        logs = event_filter.get_all_entries()
        return [self._format_event(contract, log) for log in logs]


    def parse_log(self, contract: Contract, log):
        for event_name in dir(contract.events):
            event = getattr(contract.events, event_name, None)
            if event:
                try:
                    parsed_log = event().process_receipt({'logs': [log]})
                    if parsed_log:
                        return parsed_log[0]  # Returning the first (and should be only) parsed entry
                except ValueError:
                    continue
        return None


    def _format_event(self, contract: Contract, log):
        parsed_log = self.parse_log(contract, log)
        print('parsed_log', parsed_log)
        print('log', log)
        if parsed_log:
            return FetchedEvent(
                event=parsed_log.args,
                topic=parsed_log.topics[0] if parsed_log.topics else None,
                name=parsed_log.event,
                block_number=log['blockNumber'],
                block_hash=log['blockHash'],
                transaction_hash=log['transactionHash'],
                address=log['address'],
                topics=log['topics'],
                data=log['data'],
            )
        else:
            raise ValueError("Failed to parse log")
