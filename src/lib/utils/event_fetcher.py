from web3 import Web3
from web3.exceptions import BadFunctionCallOutput
from typing import Any, Dict, List, Optional
import json

class EventFetcher:
    def __init__(self, provider_url: str, abi_directory: str):
        self.w3 = Web3(Web3.HTTPProvider(provider_url))
        self.abi_directory = abi_directory

    def load_abi(self, name: str) -> List[Dict[str, Any]]:
        with open(f"src/abi/{name}.json", 'r') as abi_file:
            return json.load(abi_file)

    def parse_typed_logs(self, contract_name: str, logs: List[Dict[str, Any]], event_name: str) -> List[Dict[str, Any]]:
        contract_abi = self.load_abi(contract_name)
        contract = self.w3.eth.contract(abi=contract_abi)

        parsed_logs = []
        for log in logs:
            if log['topics']:
                decoded_log = contract.events[event_name]().processLog(log)
                if decoded_log:
                    parsed_logs.append(decoded_log['args'])

        return parsed_logs

    def get_events(self, abi: List[Dict[str, Any]], address: str, event_name: str, from_block: int, to_block: int) -> List[Dict[str, Any]]:
        contract = self.w3.eth.contract(address=address, abi=abi)

        try:
            event_filter = contract.events[event_name].createFilter(
                fromBlock=from_block, toBlock=to_block
            )
        except BadFunctionCallOutput:
            # Handle cases where the event is not found in the ABI or other issues
            return []

        events = event_filter.get_all_entries()

        return self._format_events(events)

    def _format_events(self, events: List[Any]) -> List[Dict[str, Any]]:
        fetched_events = []
        for event in events:
            fetched_event = {
                'event': event['args'],
                'topic': event['topics'][0] if event['topics'] else None,
                'name': event.event,
                'blockNumber': event.blockNumber,
                'blockHash': event.blockHash.hex(),
                'transactionHash': event.transactionHash.hex(),
                'address': event.address,
                'topics': [topic.hex() for topic in event['topics']],
                'data': event['data']
            }
            fetched_events.append(fetched_event)

        return fetched_events
