import json
from web3 import Web3
from web3.contract import Contract

def load_contract(provider: Web3, contract_name: str, address: str) -> Contract:
    with open(f'src/abi/{contract_name}.json', 'r') as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get('abi'):
            raise Exception(f'No ABI found for contract: {contract_name}')
        abi = contract_data['abi']

    return provider.eth.contract(address=address, abi=abi)
    
