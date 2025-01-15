import json
from typing import Any, Dict, Iterator, List, Optional, Tuple, TypeVar, Union, cast

import rlp
from eth.vm.forks.arrow_glacier.transactions import (
    ArrowGlacierTransactionBuilder as TransactionBuilder,
)
from eth_typing import Address, ChecksumAddress, HexAddress, HexStr
from eth_utils import encode_hex
from hexbytes import HexBytes
from web3 import Web3
from web3.contract import Contract
from web3.types import ABI, AccessList, Nonce, TxParams, TxReceipt, Wei

from arbitrum_py import PROJECT_DIRECTORY
from arbitrum_py.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from arbitrum_py.utils.arb_provider import ArbitrumProvider

T = TypeVar("T")


def format_contract_output(contract: Contract, function_name: str, output: Any) -> Union[Dict[str, Any], Any]:
    """
    Format contract function output according to ABI specification.

    Args:
        contract: Web3 Contract instance
        function_name: Name of the function to format output for
        output: Raw output from contract function call

    Returns:
        Formatted output according to ABI specification

    Raises:
        ValueError: If function not found in contract ABI
    """
    func_abi = next(
        (item for item in contract.abi if item.get("name") == function_name and item.get("type") == "function"),
        None,
    )
    if not func_abi:
        raise ValueError(f"Function {function_name} not found in contract ABI")

    def format_output(abi_outputs: List[Dict[str, Any]], output_values: List[Any]) -> Union[Dict[str, Any], Any]:
        if not isinstance(abi_outputs, list) or not abi_outputs:
            return output_values
        if (
            len(abi_outputs) == 1
            and abi_outputs[0].get("type", "").startswith("tuple")
            and not abi_outputs[0].get("name")
        ):
            return format_output(abi_outputs[0].get("components", []), output_values)

        formatted_output: Dict[str, Any] = {}
        for i, output in enumerate(abi_outputs):
            output_type = output.get("type", "")
            output_name = output.get("name", f"output_{i}")

            if output_type == "tuple":
                formatted_output[output_name] = format_output(output.get("components", []), output_values[i])
            elif output_type == "tuple[]":
                formatted_output[output_name] = [
                    format_output(output.get("components", []), item) for item in output_values[i]
                ]
            else:
                formatted_output[output_name] = output_values[i]

        return formatted_output

    return format_output(func_abi.get("outputs", []), [output] if not isinstance(output, (list, tuple)) else output)


def to_checksum_address(address: Union[str, HexAddress]) -> ChecksumAddress:
    if Web3.is_address(address):
        return Web3.to_checksum_address(address)
    else:
        raise ValueError(f"Invalid Ethereum address: {address}")


def parse_raw_tx_pyevm(raw_tx):
    return TransactionBuilder().decode(raw_tx)


def get_contract_address(sender_address: Union[str, HexAddress], nonce: Nonce) -> ChecksumAddress:
    """Compute the contract address like Ethereum does."""
    encoded_data = rlp.encode([bytes.fromhex(sender_address[2:]), nonce])
    hashed_data = Web3.solidity_keccak(["bytes"], [encoded_data])
    contract_address = hashed_data[-20:].hex()
    return Web3.to_checksum_address(contract_address)


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
        "to": (
            Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
            if (tx.to.hex() == "0x" or tx.to.hex() == "")
            else Web3.to_checksum_address(tx.to)
        ),
        "transactionIndex": None,
        "type": tx.type_id,
        "v": None,
        "value": cast(Wei, tx.value),
    }


class ContractLoadError(Exception):
    """Custom exception for contract loading errors"""

    pass


def get_normalized_provider(provider: Union[Web3, SignerOrProvider, ArbitrumProvider]) -> Optional[Web3]:
    """Normalize different provider types to Web3 instance"""
    if isinstance(provider, SignerOrProvider):
        return provider.provider
    elif isinstance(provider, ArbitrumProvider):
        return provider.provider
    elif isinstance(provider, Web3):
        return provider
    return provider


def load_contract_data(contract_name: str, custom_path: Optional[str] = None) -> Tuple[ABI, Optional[HexStr]]:
    """
    Load contract ABI and bytecode from JSON file

    Args:
        contract_name: Name of the contract

    Returns:
        Tuple of (ABI, bytecode)

    Raises:
        ContractLoadError: If ABI file not found or invalid
    """
    base_path = PROJECT_DIRECTORY / "abi"
    file_path = base_path / f"{contract_name}.json"
    if custom_path:
        file_path = custom_path
    try:
        with open(file_path) as abi_file:
            contract_data = json.load(abi_file)
    except FileNotFoundError:
        raise ContractLoadError(f"Contract ABI file not found: {file_path}")
    except json.JSONDecodeError:
        raise ContractLoadError(f"Invalid JSON in contract ABI file: {file_path}")

    abi = contract_data.get("abi")
    if not abi:
        raise ContractLoadError(f"No ABI found for contract: {contract_name}")

    bytecode = contract_data.get("bytecode", None)
    return abi, bytecode


def normalize_contract_address(address: Union[str, Contract, Address]) -> ChecksumAddress:
    """Convert various address formats to checksum address"""
    if isinstance(address, str):
        return Web3.to_checksum_address(address)
    elif isinstance(address, Contract):
        return Web3.to_checksum_address(address.address)
    return Web3.to_checksum_address(address)


def create_contract_instance(contract_name: str) -> Contract:
    """
    Create a contract instance without provider for decoding function calls.

    Args:
        contract_name (str): Name of the contract.

    Returns:
        Contract: Contract instance for decoding calls.
    """
    abi, _ = load_contract_data(contract_name)
    w3 = Web3()  # Dummy Web3 instance for ABI decoding
    contract = w3.eth.contract(abi=abi)
    return cast(Contract, contract)


def load_contract_by_abi(
    contract_data: Dict[str, Any],
    provider: Optional[Union[Web3, SignerOrProvider, ArbitrumProvider]] = None,
    address: Optional[Union[str, Contract, Address]] = None,
):
    abi = contract_data.get("abi")
    if not abi:
        raise ContractLoadError("No ABI found for contract")

    bytecode = contract_data.get("bytecode", None)

    if provider is None:
        w3 = Web3()
        contract = w3.eth.contract(abi=abi)
        return cast(Contract, contract)

    web3_provider = get_normalized_provider(provider)
    if web3_provider is None:
        raise ContractLoadError("No valid provider found")

    if address is not None:
        contract_address = normalize_contract_address(address)
        contract = web3_provider.eth.contract(address=contract_address, abi=abi)
        return cast(Contract, contract)

    contract = (
        web3_provider.eth.contract(abi=abi, bytecode=bytecode) if bytecode else web3_provider.eth.contract(abi=abi)
    )
    return cast(Contract, contract)


def load_contract(
    contract_name: str,
    provider: Optional[Union[Web3, SignerOrProvider, ArbitrumProvider]] = None,
    address: Optional[Union[str, Contract, Address]] = None,
) -> Contract:
    """
    Load a contract instance

    Args:
        contract_name: Name of the contract
        provider: Web3 provider instance (optional if only interface needed)
        address: Contract address (optional)

    Returns:
        Contract instance or interface

    Raises:
        ContractLoadError: If contract loading fails
    """
    if provider is None:
        return create_contract_instance(contract_name)

    web3_provider = get_normalized_provider(provider)
    if web3_provider is None:
        raise ContractLoadError("No valid provider found")

    abi, bytecode = load_contract_data(contract_name)

    if address is not None:
        contract_address = normalize_contract_address(address)
        contract = web3_provider.eth.contract(address=contract_address, abi=abi)
        return cast(Contract, contract)

    contract = (
        web3_provider.eth.contract(abi=abi, bytecode=bytecode) if bytecode else web3_provider.eth.contract(abi=abi)
    )
    return cast(Contract, contract)


def deploy_abi_contract(
    provider: Union[Web3, SignerOrProvider],
    deployer: SignerOrProvider,
    contract_name: str,
    constructor_args: Optional[List[Any]] = None,
    **tx_params: Any,
) -> Contract:
    web3_provider = get_normalized_provider(provider)
    if web3_provider is None:
        raise ContractLoadError("No valid provider found")

    deployer_account = SignerProviderUtils.get_signer(deployer)

    abi, bytecode = load_contract_data(contract_name)
    if not bytecode:
        raise ContractLoadError(f"No bytecode found for contract: {contract_name}")

    contract = web3_provider.eth.contract(abi=abi, bytecode=bytecode)

    try:
        tx_params = {"from": deployer_account.address, **tx_params}
        if "nonce" not in tx_params:
            tx_params["nonce"] = web3_provider.eth.get_transaction_count(deployer_account.address)

        constructor_args = constructor_args or []

        tx = contract.constructor(*constructor_args).build_transaction(tx_params)
        signed_tx = deployer_account.sign_transaction(tx)
        tx_hash = web3_provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        tx_receipt = web3_provider.eth.wait_for_transaction_receipt(tx_hash)

        if not tx_receipt.contractAddress:
            raise ContractLoadError("Contract deployment failed: no contract address in receipt")
        deployed_contract = web3_provider.eth.contract(address=tx_receipt.contractAddress, abi=abi)
        return cast(Contract, deployed_contract)
    except Exception as e:
        raise ContractLoadError(f"Contract deployment failed: {str(e)}") from e


def is_contract_deployed(provider: Web3, address: Union[str, HexAddress]) -> bool:
    bytecode = provider.eth.get_code(Web3.to_checksum_address(address))
    return bytecode != "0x" and len(bytecode) > 2


def sign_and_sent_raw_transaction(signer: SignerOrProvider, tx: TxParams) -> TxReceipt:
    if not signer.provider:
        raise ValueError("No provider found in signer")
    if not signer.account:
        raise ValueError("No account found in signer")

    if "gasPrice" not in tx:
        if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
            pass
        else:
            tx["gasPrice"] = signer.provider.eth.gas_price

    if "nonce" not in tx:
        tx["nonce"] = signer.provider.eth.get_transaction_count(signer.account.address)

    if "chainId" not in tx:
        tx["chainId"] = signer.provider.eth.chain_id

    gas_estimate = signer.provider.eth.estimate_gas(cast(TxParams, tx))
    tx["gas"] = gas_estimate

    signed_tx = signer.account.sign_transaction(tx)
    tx_hash = signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_receipt = signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt


class CaseDict:

    SPECIAL_CASES: Dict[str, str] = {
        "erc20": "Erc20",
    }

    def __init__(self, x: Dict[str, Any]) -> None:
        for key, value in x.items():
            self.__setitem__(key, value)

    def __setitem__(self, key: str, value: Any) -> None:
        self.__setattr__(key, value)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __getattr__(self, name: str) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass
        camel_case_name = self.snake_to_camel(name)
        try:
            return super().__getattribute__(camel_case_name)
        except AttributeError:
            pass

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @classmethod
    def snake_to_camel(cls, name: str) -> str:
        components = name.split("_")
        result = components[0]  # First component stays lowercase
        # Process remaining components
        for component in components[1:]:
            # Check if component is in special cases
            if component in CaseDict.SPECIAL_CASES:
                result += CaseDict.SPECIAL_CASES[component]
            else:
                result += component.title()
        return result

    @classmethod
    def camel_to_snake(cls, name: str) -> str:
        # First handle special cases
        for camel, snake in CaseDict.SPECIAL_CASES.items():
            name = name.replace(camel, snake)

        # Convert the remaining camelCase to snake_case
        snake_case = ""
        for i, char in enumerate(name):
            if i > 0 and char.isupper():
                # Check if this uppercase letter is part of a sequence of uppercase letters
                if not name[i - 1].isupper():  # Only add underscore if previous char wasn't uppercase
                    snake_case += "_"
            snake_case += char.lower()

        return snake_case

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        return getattr(self, key, default)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dict__)

    def keys(self) -> List[str]:
        return list(self.__dict__.keys())

    def items(self) -> List[Tuple[str, Any]]:
        return list(self.__dict__.items())

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__

    def __setattr__(self, name: str, value: Any) -> None:
        if isinstance(value, dict):
            value = CaseDict(value)
        elif isinstance(value, list):
            value = [CaseDict(item) if isinstance(item, dict) else item for item in value]
        camel_case_name = self.snake_to_camel(name)
        super().__setattr__(camel_case_name, value)

    def __str__(self) -> str:
        return str(self.to_dict())

    def convert_to_serializable(self, value: Any) -> Any:
        return self._convert_value(value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert CaseDict to a regular dict for JSON serialization"""
        result: Dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if not k.startswith("_"):
                result[k] = self._convert_value(v)
        return result

    def _convert_value(self, value: Any) -> Any:
        """Helper method to convert values for serialization"""
        if isinstance(value, CaseDict):
            return value.to_dict()
        elif isinstance(value, list):
            return [self._convert_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._convert_value(v) for k, v in value.items()}
        elif hasattr(value, "hex"):  # Handle Web3 types like HexBytes
            return value.hex()
        else:
            return value


class CaseDictEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, CaseDict):
            return obj.to_dict()
        elif hasattr(obj, "hex"):  # Handle Web3 types
            return obj.hex()
        return super().default(obj)
