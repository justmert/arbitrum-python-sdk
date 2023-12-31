import json
from web3 import Web3
from web3.contract import Contract

def load_contract(provider: Web3, contract_name: str, address: str, is_classic = False) -> Contract:
    if is_classic:
        file_path = f'src/abi/classic/{contract_name}.json'
    else:
        file_path = f'src/abi/{contract_name}.json'
    
    if isinstance(address, str):
        contract_address = Web3.to_checksum_address(address)

    elif isinstance(address, Contract):
        contract_address = Web3.to_checksum_address(address.address)
    
    else:
        contract_address = address

    with open(file_path, 'r') as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get('abi'):
            raise Exception(f'No ABI found for contract: {contract_name}')
        abi = contract_data['abi']

    return provider.eth.contract(address=contract_address, abi=abi)


def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs"}
    components = name.split('_')
    # Convert the first component as is, then title-case the remaining components
    camel_case_name = components[0] + ''.join(special_cases.get(x, x.title()) for x in components[1:])
    return camel_case_name


class CamelSnakeCaseMixin:
    def __getitem__(self, key):
        return self.__getattr__(key)

    def __getattr__(self, name):
        # Try to fetch the attribute as is (for camelCase or any other case)
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass
        
        # Convert snake_case to camelCase and try again
        camel_case_name = snake_to_camel(name)
        try:
            return super().__getattribute__(camel_case_name)
        except AttributeError:
            pass

        # If not found, raise AttributeError
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        # Ensure attributes are stored in camelCase
        if '_' in name:
            name = snake_to_camel(name)
        
        super().__setattr__(name, value)
