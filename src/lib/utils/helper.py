import json
from web3 import Web3
from web3.contract import Contract
from web3 import Account

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from hexbytes import HexBytes
from web3 import Web3
from web3.types import AccessList, Nonce, TxData, Wei
from eth_utils import encode_hex, to_bytes
from eth.abc import SignedTransactionAPI
from eth.vm.forks.arrow_glacier.transactions import (
    ArrowGlacierTransactionBuilder as TransactionBuilder,
)
from typing import Any, Dict, cast
import rlp
import re

def get_address(address):
    # Validate if input is a string
    if not isinstance(address, str):
        raise ValueError("Invalid address: not a string")

    # Check if it's a valid Ethereum address or ICAP
    if re.match(r'^(0x)?[0-9a-fA-F]{40}$', address):
        # Add '0x' prefix if missing
        if not address.startswith('0x'):
            address = '0x' + address

        # Checksum the address
        try:
            return Web3.to_checksum_address(address)
        except ValueError:
            raise ValueError("Bad address checksum")
    elif re.match(r'^XE[0-9]{2}[0-9A-Za-z]{30,31}$', address):
        # Handle ICAP addresses (simplified, as full ICAP support is complex)
        raise NotImplementedError("ICAP addresses not fully supported")
    else:
        raise ValueError
        
def parse_raw_tx_pyevm(raw_tx: str) -> SignedTransactionAPI:
    """Convert a raw transaction to a py-evm signed transaction object.

    Inspired by:
     - https://github.com/ethereum/web3.py/issues/3109#issuecomment-1737744506
     - https://snakecharmers.ethereum.org/web3-py-patterns-decoding-signed-transactions/
    """
    return TransactionBuilder().decode(raw_tx)


def get_contract_address(sender_address, nonce):
    """Compute the contract address like Ethereum does."""
    # RLP-encode the sender address and nonce
    encoded_data = rlp.encode([bytes.fromhex(sender_address[2:]), nonce])
    # Keccak hash the encoded data
    hashed_data = Web3.solidity_keccak(['bytes'], [encoded_data])
    # The contract address is the last 20 bytes of the hash
    contract_address = hashed_data[-20:].hex()
    return contract_address


def parse_raw_tx(raw_tx: str) -> TxData:
    """Convert a raw transaction to a web3.py TxData dict.

    Inspired by:
     - https://ethereum.stackexchange.com/a/83855/89782
     - https://docs.ethers.org/v5/api/utils/transactions/#utils-parseTransaction
    """
    tx = parse_raw_tx_pyevm(raw_tx)
    return {
        "accessList": cast(AccessList, tx.access_list),
        "blockHash": None,
        "blockNumber": None,
        "chainId": tx.chain_id,
        "data": HexBytes(Web3.to_hex(tx.data)),
        "from": Web3.to_checksum_address(encode_hex(tx.sender)),
        "gas": tx.gas,
        "gasPrice": None if tx.type_id is not None else cast(Wei, tx.gas_price),
        "maxFeePerGas": cast(Wei, tx.max_fee_per_gas),
        "maxPriorityFeePerGas": cast(Wei, tx.max_priority_fee_per_gas),
        "hash": HexBytes(tx.hash),
        "input": None,
        "nonce": cast(Nonce, tx.nonce),
        "r": HexBytes(tx.r),
        "s": HexBytes(tx.s),
        "to": Web3.to_checksum_address("0x0000000000000000000000000000000000000000") if (tx.to.hex() == "0x" or tx.to.hex() == "") else Web3.to_checksum_address(tx.to),
        "transactionIndex": None,
        "type": tx.type_id,
        "v": None,
        "value": cast(Wei, tx.value),
    }


def load_contract(
    provider: Web3, contract_name: str, address: str = None, is_classic: bool = False
) -> Contract:
    
    if isinstance(provider, SignerOrProvider):
        provider = provider.provider

    else:
        provider = provider

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
) -> Contract:
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
    
    # Create a new contract instance at the deployed address
    deployed_contract = provider.eth.contract(
        address=contract_address,
        abi=contract.abi
    )

    return deployed_contract

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

def sign_and_sent_raw_transaction(signer: SignerOrProvider, tx: dict):
    # Build the transaction
    
    if 'gasPrice' not in tx:
        tx['gasPrice'] = signer.provider.eth.gas_price

    if 'nonce' not in tx:
        tx['nonce'] = signer.provider.eth.get_transaction_count(signer.account.address)

    if 'chainId' not in tx:
        tx['chainId'] = signer.provider.eth.chain_id

    gas_estimate = signer.provider.eth.estimate_gas(tx)

    tx['gas'] = gas_estimate

    signed_tx = signer.account.sign_transaction(tx)

    # Send the raw transaction
    tx_hash = signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

    tx_receipt = signer.provider.eth.wait_for_transaction_receipt(tx_hash)
    print("tx_receipt", tx_receipt)

    # Return the transaction receipt
    return tx_receipt

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
