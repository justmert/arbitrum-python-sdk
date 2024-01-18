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

def load_abi(contract_name: str, is_classic = False) -> Contract:
    if is_classic:
        file_path = f'src/abi/classic/{contract_name}.json'
    else:
        file_path = f'src/abi/{contract_name}.json'
    
    with open(file_path, 'r') as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get('abi'):
            raise Exception(f'No ABI found for contract: {contract_name}')
        
        abi = contract_data['abi']
    return abi

def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs", 'erc20': "ERC20"}
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

    def to_dict(self):
        return {attr: self.convert_to_serializable(getattr(self, attr)) for attr in self.__dict__}


    def convert_to_serializable(self, value):
        # If the value is an instance of CamelSnakeCaseMixin, convert it to a dictionary
        if isinstance(value, CamelSnakeCaseMixin):
            return value.to_dict()
        # If the value is a list, apply this conversion to each element
        elif isinstance(value, list):
            return [self.convert_to_serializable(item) for item in value]
        # If the value is a dictionary, apply this conversion to each value
        elif isinstance(value, dict):
            return {key: self.convert_to_serializable(val) for key, val in value.items()}
    
        elif isinstance(value, Contract):
            return value.address
        else:
            return value
        

class CaseDict(CamelSnakeCaseMixin):
    def __init__(self, x):
        self._data = {}
        for key, value in x.items():
            self._data[key] = value
            setattr(self, key, value)

    def __setitem__(self, key, value):
        self._data[key] = value
        setattr(self, key, value)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def __contains__(self, key):
        return key in self._data

    def to_dict(self):
        return self._data

    def __str__(self):
        items = [f"{key}: {value}" for key, value in self._data.items()]
        return f"CaseDict({', '.join(items)})"
