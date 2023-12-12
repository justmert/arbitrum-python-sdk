from web3 import Web3
from web3.contract import Contract

class EventFetcher:
    def __init__(self, provider_url):
        self.w3 = Web3(Web3.HTTPProvider(provider_url))

    def get_events(self, abi, address, event_name, from_block, to_block):
        contract = self.w3.eth.contract(address=address, abi=abi)
        event_filter = contract.events[event_name].createFilter(
            fromBlock=from_block, toBlock=to_block
        )
        events = event_filter.get_all_entries()

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
