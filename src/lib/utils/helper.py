import json
from web3 import Web3
from web3.contract import Contract

def load_contract(contract_name: str, address: str, web3_instance: Web3) -> Contract:
    with open(f'src/abi/{contract_name}.json', 'r') as abi_file:
        abi = json.load(abi_file)
    return web3_instance.eth.contract(address=address, abi=abi)
