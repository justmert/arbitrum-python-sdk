from web3 import Web3
from web3.types import LogReceipt
from web3.exceptions import BadFunctionCallOutput
from typing import Any, Dict, List, Optional
import json
from src.lib.data_entities.errors import ArbSdkError

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import load_contract
from web3.contract import Contract

class FetchedEvent:
    def __init__(self, event, topic, name, block_number, block_hash, transaction_hash, address, topics, data):
        self.event = event
        self.topic = topic
        self.name = name
        self.block_number = block_number
        self.block_hash = block_hash
        self.transaction_hash = transaction_hash
        self.address = address
        self.topics = topics
        self.data = data

class EventFetcher():

    def __init__(self, provider):
        if isinstance(provider, str):
            self.provider = Web3(Web3.HTTPProvider(provider))

        elif isinstance(provider, Web3):
            self.provider = provider
            
        elif isinstance(provider, SignerOrProvider):
            self.provider = provider.provider

        else:
            raise Exception("Invalid provider type")


    # def get_events(self, contract, topic_generator, str,
    #                filter_params):
        
    #     contract = self.provider.eth.contract(address=filter_params.get('address', '0x0000000000000000000000000000000000000000'), abi=contract.abi)

    #     event_filter = topic_generator(contract)
    #     full_filter = dict(**event_filter, **filter_params)
    #     logs = self.provider.eth.get_logs(full_filter)

    #     fetched_events = []
    #     for log in logs:
    #         if log.get('removed', False):
    #             continue

    #         p_log = contract.events[event_filter.event_name]().processLog(log)
    #         fetched_event = FetchedEvent(
    #             event=p_log['args'],
    #             topic=p_log['topics'][0] if p_log['topics'] else None,
    #             name=p_log['event'],
    #             block_number=log['blockNumber'],
    #             block_hash=log['blockHash'],
    #             transaction_hash=log['transactionHash'],
    #             address=log['address'],
    #             topics=log['topics'],
    #             data=log['data']
    #         )
    #         fetched_events.append(fetched_event)

    #     return fetched_events


    # def get_events(self, abi: List[Dict[str, Any]], address: str, event_name: str, from_block: int, to_block: int) -> List[Dict[str, Any]]:
    #     contract = self.w3.eth.contract(address=address, abi=abi)

    #     try:
    #         event_filter = contract.events[event_name].create_filter(
    #             fromBlock=from_block, toBlock=to_block
    #         )
    #     except BadFunctionCallOutput:
    #         # Handle cases where the event is not found in the ABI or other issues
    #         return []

    #     events = event_filter.get_all_entries()

    #     return self._format_events(events)

    # def _format_events(self, events: List[Any]) -> List[Dict[str, Any]]:
    #     fetched_events = []
    #     for event in events:
    #         fetched_event = {
    #             'event': event['args'],
    #             'topic': event['topics'][0] if event['topics'] else None,
    #             'name': event.event,
    #             'blockNumber': event.blockNumber,
    #             'blockHash': event.blockHash.hex(),
    #             'transactionHash': event.transactionHash.hex(),
    #             'address': event.address,
    #             'topics': [topic.hex() for topic in event['topics']],
    #             'data': event['data']
    #         }
    #         fetched_events.append(fetched_event)

    #     return fetched_events

    async def get_events(self, contract_factory, topic_generator, filter, is_classic=False):
        # Assuming contract_factory is a factory method or class to create a contract instance
        # and topic_generator is a function that takes a contract and returns a filter object
        contract_address = filter.get('address', Web3.to_checksum_address('0x0000000000000000000000000000000000000000'))
        # contract = contract_factory(contract_address, self.provider)

        if isinstance(contract_factory, str):
            contract = load_contract(provider=self.provider, contract_name=contract_factory, address=contract_address, is_classic=is_classic)
        
        elif isinstance(contract_factory, Contract):
            contract = contract_factory
        else:
            raise ArbSdkError("Invalid contract factory type")
        
        events = topic_generator(contract).get_all_entries()

        return  [{'event': event.args, 'transactionHash': event.transactionHash} for event in events]
