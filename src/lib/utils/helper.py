import json
from web3 import Web3
from web3.contract import Contract
from web3 import Account


def load_contract(
    provider: Web3, contract_name: str, address: str = None, is_classic: bool = False
) -> Contract:
    if is_classic:
        file_path = f"src/abi/classic/{contract_name}.json"
    else:
        file_path = f"src/abi/{contract_name}.json"

    with open(file_path, "r") as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get("abi"):
            raise Exception(f"No ABI found for contract: {contract_name}")
        abi = contract_data.get("abi", None)
        bytecode = contract_data.get("bytecode", None)

    if address is not None:
        if isinstance(address, str):
            contract_address = Web3.to_checksum_address(address)

        elif isinstance(address, Contract):
            contract_address = Web3.to_checksum_address(address.address)

        else:
            contract_address = address

        return provider.eth.contract(address=contract_address, abi=abi)

    else:
        return provider.eth.contract(abi=abi, bytecode=bytecode)


def deploy_abi_contract(
    provider: Web3,
    deployer: Account,
    contract_name: str,
    is_classic=False,
    constructor_args=[],
):
    contract = load_contract(
        provider=provider, contract_name=contract_name, is_classic=is_classic
    )
    chain_id = provider.eth.chain_id
    gas_estimate = contract.constructor(*constructor_args).estimate_gas(
        {"from": deployer.address}
    )
    construct_txn = contract.constructor(*constructor_args).build_transaction(
        {
            "from": deployer.address,
            "nonce": provider.eth.get_transaction_count(deployer.address),
            "gas": gas_estimate,  # Use the estimated gas limit
            "gasPrice": provider.eth.gas_price,
            "chainId": chain_id,  # Include the chain ID
        }
    )
    signed_txn = deployer.sign_transaction(construct_txn)
    tx_hash = provider.eth.send_raw_transaction(signed_txn.rawTransaction)
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print('txxx', tx_receipt)
    return contract_address


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

def is_contract_deployed(w3, address):
    # Get the bytecode of the contract at the specified address
    bytecode = w3.eth.get_code(Web3.to_checksum_address(address))
    print("byr", bytecode)
    # If bytecode is '0x' or empty, it means no contract is deployed
    return bytecode != '0x' and len(bytecode) > 2


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
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

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
        return {
            k: self.convert_to_serializable(v)
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

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
            return {
                key: self.convert_to_serializable(val) for key, val in value.items()
            }
        elif isinstance(value, Contract):
            return value.address
        else:
            return value
