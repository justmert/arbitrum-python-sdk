from decimal import Decimal
from typing import Any, Callable, Dict, List, Literal, Optional, TypeVar, Union

from eth_utils import int_to_big_endian
from web3 import Web3
from web3.types import Wei

from arbitrum_py.data_entities.constants import ARB_ADDRESS_TABLE_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.utils.helper import load_contract

# Type definitions
PrimitiveType = Union[str, int, bool, Wei, Decimal]
PrimitiveOrArray = Union[PrimitiveType, List[PrimitiveType]]
BytesSize = Literal[1, 4, 8, 16, 32]
AddressIndexMemo = Dict[str, int]

# Global memo for address indices
address_to_index_memo: AddressIndexMemo = {}


def get_address_index(address: str, provider: Any) -> int:
    """
    Check if an address is registered in the Arbitrum address table contract.

    This function checks the ArbAddressTable contract to see if an address is registered.
    If found, returns its index. Results are memoized to avoid redundant contract calls.

    Args:
        address: The Ethereum address to look up
        provider: Web3 provider connected to L2

    Returns:
        int: The index if address is registered, -1 if not registered

    Note:
        The function caches results in address_to_index_memo to optimize repeated lookups
    """
    if address in address_to_index_memo:
        return address_to_index_memo[address]

    arb_address_table = load_contract(
        provider=provider,
        contract_name="ArbAddressTable",
        address=ARB_ADDRESS_TABLE_ADDRESS,
    )

    is_registered = arb_address_table.functions.addressExists(address).call()

    if is_registered:
        index = arb_address_table.functions.lookup(address).call()
        address_to_index_memo[address] = index
        return index
    else:
        return -1


def arg_serializer_constructor(provider: Any) -> Callable[[List[PrimitiveOrArray]], bytes]:
    """
    Create a function for serializing parameters using the Arbitrum address table.

    This constructor creates a closure over a provider that can be used to serialize
    parameters according to the Arbitrum byte serialization schema.

    Args:
        provider: Web3 provider or wrapper connected to L2

    Returns:
        Callable: A function that takes a list of primitives or arrays and returns serialized bytes

    Example:
        >>> provider = Web3(Web3.HTTPProvider('...'))
        >>> serializer = arg_serializer_constructor(provider)
        >>> result = serializer(['0x123...', 42, True])
    """

    def serialize_params_with_index(params: List[PrimitiveOrArray]) -> bytes:
        def address_to_index(address: str) -> int:
            return get_address_index(address, provider)

        return serialize_params(params, address_to_index)

    return serialize_params_with_index


def is_address_type(value: Any) -> bool:
    """
    Check if a value is a valid Ethereum address.

    Args:
        value: Any value to check

    Returns:
        bool: True if value is a string and valid Ethereum address, False otherwise
    """
    return isinstance(value, str) and Web3.is_address(value)


def to_uint(val: Union[PrimitiveType, int], bytes_size: BytesSize) -> bytes:
    """
    Convert a value to a big-endian byte representation with specified size.

    Args:
        val: Value to convert (numeric or boolean)
        bytes_size: Size of the resulting byte array (1, 4, 8, 16, or 32)

    Returns:
        bytes: Big-endian representation of the value

    Note:
        Booleans are converted to 1 (True) or 0 (False)
    """
    if isinstance(val, bool):
        val = 1 if val else 0
    as_int = int(val)
    return int_to_big_endian(as_int).rjust(bytes_size, b"\0")


def format_primitive(value: PrimitiveType) -> bytes:
    """
    Format a primitive value according to the Arbitrum byte serialization schema.

    This function handles the following types:
    - Ethereum addresses (as 20-byte values)
    - Booleans (as 1 = True, 0 = False)
    - Numbers (as 32-byte big-endian values)

    Args:
        value: The primitive value to format

    Returns:
        bytes: Formatted byte representation

    Raises:
        ArbSdkError: If the value type is not supported
    """
    if is_address_type(value):
        return Web3.to_bytes(hexstr=value)  # raw 20 bytes
    elif isinstance(value, (bool, int)) or (isinstance(value, str) and value.isdigit()):
        return to_uint(value, 32)
    else:
        raise ArbSdkError("Unsupported type for format_primitive()")


def serialize_params(params: List[PrimitiveOrArray], address_to_index: Callable[[str], int] = lambda addr: -1) -> bytes:
    """
    Serialize parameters according to the Arbitrum byte serialization schema.

    Schema for address arrays:
    - 1 byte: array length
    - 1 byte: is-registered flag (1 = all registered, 0 = not all registered)
    - For each address:
        - If registered: 4 bytes (index)
        - If not registered: 20 bytes (full address)

    Schema for non-address arrays:
    - 1 byte: array length
    - Concatenated items (variable length)

    Schema for single address:
    - 1 byte: is-registered flag
    - 4 or 20 bytes: index or address

    Args:
        params: List of values to serialize (can include nested lists)
        address_to_index: Function to get address table index (-1 if not registered)

    Returns:
        bytes: Serialized parameter data

    Example:
        >>> serialize_params(['0x123...', [42, 43], True])
    """
    formatted_parts: List[bytes] = []

    for param in params:
        if isinstance(param, list):
            array_length = len(param)
            formatted_parts.append(to_uint(array_length, 1))

            if array_length > 0 and is_address_type(param[0]):
                indices = [address_to_index(addr) for addr in param]

                if all(i > -1 for i in indices):
                    formatted_parts.append(to_uint(1, 1))
                    for idx in indices:
                        formatted_parts.append(to_uint(idx, 4))
                else:
                    formatted_parts.append(to_uint(0, 1))
                    for addr in param:
                        formatted_parts.append(format_primitive(addr))
            else:
                for item in param:
                    formatted_parts.append(format_primitive(item))
        else:
            if is_address_type(param):
                idx = address_to_index(param)
                if idx > -1:
                    formatted_parts.append(to_uint(1, 1))
                    formatted_parts.append(to_uint(idx, 4))
                else:
                    formatted_parts.append(to_uint(0, 1))
                    formatted_parts.append(format_primitive(param))
            else:
                formatted_parts.append(format_primitive(param))

    return b"".join(formatted_parts)
