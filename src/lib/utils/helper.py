import json
from web3 import Web3
from web3.contract import Contract


def load_contract(
    provider: Web3, contract_name: str, address: str, is_classic=False
) -> Contract:
    if is_classic:
        file_path = f"src/abi/classic/{contract_name}.json"
    else:
        file_path = f"src/abi/{contract_name}.json"

    if isinstance(address, str):
        contract_address = Web3.to_checksum_address(address)

    elif isinstance(address, Contract):
        contract_address = Web3.to_checksum_address(address.address)

    else:
        contract_address = address

    with open(file_path, "r") as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get("abi"):
            raise Exception(f"No ABI found for contract: {contract_name}")
        abi = contract_data["abi"]

    return provider.eth.contract(address=contract_address, abi=abi)


def load_abi(contract_name: str, is_classic=False) -> Contract:
    if is_classic:
        file_path = f"src/abi/classic/{contract_name}.json"
    else:
        file_path = f"src/abi/{contract_name}.json"

    with open(file_path, "r") as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get("abi"):
            raise Exception(f"No ABI found for contract: {contract_name}")

        abi = contract_data["abi"]
    return abi


def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs", "erc20": "ERC20"}
    components = name.split("_")
    # Convert the first component as is, then title-case the remaining components
    camel_case_name = components[0] + "".join(
        special_cases.get(x, x.title()) for x in components[1:]
    )
    return camel_case_name


class CaseDict:
    def __init__(self, x):
        for key, value in x.items():
            setattr(self, key, value)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

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

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def items(self):
        return self.__dict__.items()

    def __contains__(self, key):
        return key in self.__dict__

    def __setattr__(self, name, value):
        camel_case_name = snake_to_camel(name)
        super().__setattr__(camel_case_name, value)

    def to_dict(self):
        # Convert all attributes (except special ones) to a dictionary
        return {k: self.convert_to_serializable(v) for k, v in self.__dict__.items() if not k.startswith('_')}

    def __str__(self):
        items = [f"{key}: {value}" for key, value in self.to_dict().items()]
        return f"CaseDict({', '.join(items)})"

    def convert_to_serializable(self, value):
        # Conversion logic remains the same
        if isinstance(value, CaseDict):
            return value.to_dict()
        elif isinstance(value, list):
            return [self.convert_to_serializable(item) for item in value]
        elif isinstance(value, dict):
            return {key: self.convert_to_serializable(val) for key, val in value.items()}
        elif isinstance(value, Contract):
            return value.address
        else:
            return value
