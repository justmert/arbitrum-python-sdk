import json
from typing import cast

import rlp
from eth.vm.forks.arrow_glacier.transactions import (
    ArrowGlacierTransactionBuilder as TransactionBuilder,
)
from eth_utils import encode_hex
from hexbytes import HexBytes
from web3 import Web3
from web3.contract import Contract
from web3.types import AccessList, Nonce, Wei

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.arb_provider import ArbitrumProvider


def format_contract_output(contract, function_name, output):
    func_abi = next(
        (item for item in contract.abi if item.get("name") == function_name and item.get("type") == "function"),
        None,
    )
    if not func_abi:
        raise ValueError(f"Function {function_name} not found in contract ABI")

    def format_output(abi_outputs, output_values):
        if not isinstance(abi_outputs, list) or not abi_outputs:
            return output_values
        if len(abi_outputs) == 1 and abi_outputs[0].get("type").startswith("tuple") and not abi_outputs[0].get("name"):
            return format_output(abi_outputs[0].get("components", []), output_values)

        formatted_output = {}
        for i, output in enumerate(abi_outputs):
            output_type = output.get("type")
            output_name = output.get("name", f"output_{i}")

            if output_type.startswith("tuple"):
                if isinstance(output_values, list) or isinstance(output_values, tuple):
                    formatted_output[output_name] = format_output(output.get("components", []), output_values[i])
                else:
                    formatted_output[output_name] = format_output(output.get("components", []), output_values)
            else:
                formatted_output[output_name] = output_values[i]

        return formatted_output

    return format_output(func_abi.get("outputs", []), output)


def get_address(address):
    if Web3.is_address(address):
        return Web3.to_checksum_address(address)
    else:
        raise ValueError(f"Invalid Ethereum address: {address}")


def parse_raw_tx_pyevm(raw_tx):
    return TransactionBuilder().decode(raw_tx)


def get_contract_address(sender_address, nonce):
    """Compute the contract address like Ethereum does."""
    encoded_data = rlp.encode([bytes.fromhex(sender_address[2:]), nonce])
    hashed_data = Web3.solidity_keccak(["bytes"], [encoded_data])
    contract_address = hashed_data[-20:].hex()
    return contract_address


def parse_raw_tx(raw_tx):
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
        "to": Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
        if (tx.to.hex() == "0x" or tx.to.hex() == "")
        else Web3.to_checksum_address(tx.to),
        "transactionIndex": None,
        "type": tx.type_id,
        "v": None,
        "value": cast(Wei, tx.value),
    }


def load_contract(contract_name, provider, address=None, is_classic=False):
    if isinstance(provider, SignerOrProvider):
        provider = provider.provider

    elif isinstance(provider, ArbitrumProvider):
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
        if not bytecode:
            return provider.eth.contract(abi=abi)
        else:
            return provider.eth.contract(abi=abi, bytecode=bytecode)


def deploy_abi_contract(
    provider,
    deployer,
    contract_name,
    constructor_args=[],
    is_classic=False,
):
    if isinstance(provider, SignerOrProvider):
        provider = provider.provider

    if isinstance(deployer, SignerOrProvider):
        deployer = deployer.account

    contract_abi, bytecode = load_abi(contract_name, is_classic=is_classic)
    contract = provider.eth.contract(abi=contract_abi, bytecode=bytecode)

    tx_hash = contract.constructor(*constructor_args).transact({"from": deployer.address})
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)
    return provider.eth.contract(address=tx_receipt.contractAddress, abi=contract_abi)


def load_abi(contract_name, is_classic=False):
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

    return abi, bytecode


def is_contract_deployed(provider, address):
    bytecode = provider.eth.get_code(Web3.to_checksum_address(address))
    return bytecode != "0x" and len(bytecode) > 2


def snake_to_camel(name):
    special_cases = {"id": "ID", "ids": "IDs", "erc20": "ERC20"}
    components = name.split("_")
    camel_case_name = components[0] + "".join(special_cases.get(x, x.title()) for x in components[1:])
    return camel_case_name


def sign_and_sent_raw_transaction(signer, tx):
    if "gasPrice" not in tx:
        if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
            pass
        else:
            tx["gasPrice"] = signer.provider.eth.gas_price

    if "nonce" not in tx:
        tx["nonce"] = signer.provider.eth.get_transaction_count(signer.account.address)

    if "chainId" not in tx:
        tx["chainId"] = signer.provider.eth.chain_id

    gas_estimate = signer.provider.eth.estimate_gas(tx)

    tx["gas"] = gas_estimate

    signed_tx = signer.account.sign_transaction(tx)

    tx_hash = signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

    tx_receipt = signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt


class CaseDict:
    def __init__(self, x):
        for key, value in x.items():
            self.__setattr__(key, value)

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __getattr__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass

        camel_case_name = snake_to_camel(name)
        try:
            return super().__getattribute__(camel_case_name)
        except AttributeError:
            pass

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
        if isinstance(value, dict):
            value = CaseDict(value)
        elif isinstance(value, list):
            value = [CaseDict(item) if isinstance(item, dict) else item for item in value]
        camel_case_name = snake_to_camel(name)
        super().__setattr__(camel_case_name, value)

    def to_dict(self):
        return {k: self.convert_to_serializable(v) for k, v in self.__dict__.items() if not k.startswith("_")}

    def __str__(self):
        items = [f"{key}: {self.convert_to_serializable(value)}" for key, value in self.to_dict().items()]
        return f"CaseDict({', '.join(items)})"

    def convert_to_serializable(self, value):
        if isinstance(value, CaseDict):
            return value.to_dict()
        elif isinstance(value, list):
            return [self.convert_to_serializable(item) for item in value]
        elif isinstance(value, Contract):
            return value.address
        else:
            return value


class CaseDictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, CaseDict):
            return obj.to_dict()

        return json.JSONEncoder.default(self, obj)
