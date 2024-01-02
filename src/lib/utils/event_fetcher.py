from web3 import Web3
from web3.types import LogReceipt
from web3.exceptions import BadFunctionCallOutput
from typing import Any, Dict, List, Optional
import json

class EventFetcher:
    def __init__(self, provider_or_url: str, abi_directory: str):
        if isinstance(provider_or_url, str):
            self.w3 = Web3(Web3.HTTPProvider(provider_or_url))
        elif isinstance(provider_or_url, Web3):
            self.w3 = provider_or_url
        self.abi_directory = abi_directory

    def load_abi(self, name: str) -> List[Dict[str, Any]]:
        # Ensure this path is correct and points to the ABI file
        print(name)
        with open(f"src/abi/{name}.json", 'r') as abi_file:
            abi_content = json.load(abi_file)
            # Ensure this extracts just the list of ABI definitions
            return abi_content['abi'] if 'abi' in abi_content else abi_content


    def parse_typed_logs(self, contract_name: str, logs: List[Dict[str, Any]], event_name: str) -> List[Dict[str, Any]]:
        contract_abi = self.load_abi(contract_name)
        contract = self.w3.eth.contract(abi=contract_abi)

        # Find the correct event ABI
        event_abi = next((event for event in contract_abi if event.get('name') == event_name and event.get('type') == 'event'), None)
        if not event_abi:
            print(f"Event {event_name} not found in ABI.")
            return []

        # Compute the expected event signature and ensure it starts with '0x'
        event_signature = Web3.keccak(text=f"{event_name}({','.join([input['type'] for input in event_abi['inputs']])})").hex()
        event_signature = event_signature[2:].lower()  # Ensure it's in lowercase and without '0x'

        parsed_logs = []
        for log in logs:
            # Normalize the log's topic by removing '0x' prefix and converting to lowercase
            log_topic = log['topics'][0][2:].lower() if log['topics'] else None
            if log_topic and log_topic == event_signature:
                try:
                    print(f"Matched! Log's Topic: 0x{log_topic} == Computed Signature: 0x{event_signature}")
                    # Create a LogReceipt object to match the expected type for process_log
                    
                    no_prefix_log = log.copy()
                    no_prefix_log['topics'] = [bytes.fromhex(topic[2:]) for topic in log['topics']]

                    log_receipt = LogReceipt(no_prefix_log)
                    decoded_log = contract.events[event_name]().process_log(log_receipt)
                    parsed_logs.append(decoded_log['args'])
                except Exception as e:
                    print(f"Failed to decode log: {e}")
                    raise e
                else:
                    pass
        print(parsed_logs)
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
