from web3 import Web3
from web3.contract import Contract

# Note: Since Python doesn't have TypeScript's typing system, we'll be using more generic Python types.

class TypeChainContractFactory:
    def __init__(self, abi, provider):
        self.abi = abi
        self.provider = provider

    def connect(self, address):
        return self.provider.eth.contract(address=address, abi=self.abi)

    def create_interface(self):
        # Note: This function should return an interface to interact with the contract.
        # In Python, this is typically handled by the Contract object from web3.py
        return self.abi


def parse_typed_log(contract_factory, log, filter_name):
    contract = contract_factory.connect(log['address'])
    event_abi = [event for event in contract_factory.abi if event['name'] == filter_name and event['type'] == 'event']
    
    if not event_abi:
        return None

    event_abi = event_abi[0]
    event_signature = Web3.keccak(text=f"{filter_name}({','.join([input['type'] for input in event_abi['inputs']])})").hex()

    if log['topics'][0] == event_signature:
        return contract.events[filter_name]().processLog(log)
    else:
        return None


def parse_typed_logs(contract_factory, logs, filter_name):
    return [parse_typed_log(contract_factory, log, filter_name) for log in logs if parse_typed_log(contract_factory, log, filter_name) is not None]
