from typing import Any, List, Union
from eth_utils import int_to_big_endian
from web3 import Web3

from src.lib.data_entities.constants import ARB_ADDRESS_TABLE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.utils.helper import load_contract

# Cache for previously looked-up addresses -> index
address_to_index_memo = {}

async def get_address_index(address: str, provider) -> int:
    """
    Check if an address is registered in the Arbitrum address table contract.
    Return its index if found, or -1 if not registered.

    :param address: The Ethereum address to look up
    :param provider: Web3 (or wrapper) connected to L2
    :return: Index if found, else -1
    """
    if address in address_to_index_memo:
        return address_to_index_memo[address]

    arb_address_table = load_contract(
        provider=provider,
        contract_name="ArbAddressTable",
        address=ARB_ADDRESS_TABLE_ADDRESS,
        is_classic=False,
    )

    is_registered = await arb_address_table.functions.addressExists(address).call()

    if is_registered:
        index = await arb_address_table.functions.lookup(address).call()
        address_to_index_memo[address] = index
        return index
    else:
        return -1

async def arg_serializer_constructor(provider):
    """
    Creates a function that can serialize parameters by 
    looking up each address in the Arbitrum address table 
    to see if it is registered.

    :param provider: Web3 provider or wrapper
    :return: A function that takes a list of primitive or array-of-primitive items 
             and returns a serialized byte array
    """
    async def serialize_params_with_index(params: List[Any]) -> bytes:
        async def address_to_index(address: str) -> int:
            return await get_address_index(address, provider)

        return await serialize_params(params, address_to_index)

    return serialize_params_with_index


def is_address_type(value: Any) -> bool:
    """
    Check if 'value' is a string that is a valid Ethereum address.
    """
    return isinstance(value, str) and Web3.is_address(value)


def to_uint(val: Any, bytes_size: int) -> bytes:
    """
    Convert a numeric or boolean to big-endian with specified size (in bytes).
    For booleans, True -> 1, False -> 0
    """
    if isinstance(val, bool):
        val = 1 if val else 0
    as_int = int(val)
    return int_to_big_endian(as_int).rjust(bytes_size, b"\0")


def format_primitive(value: Any) -> bytes:
    """
    Format a single primitive value (address, bool, number) into a 32-byte representation by default.
    (In TS, we used `BigNumber` or Ethers serialization.)
    """
    if is_address_type(value):
        # In TS code we might store the actual address, or do partial checks. 
        # Here we just hex-encode an address or do a 32-byte numeric
        # We'll do an "address as 20 bytes" or as a 32-byte for the numeric type, 
        # but the original code uses 32 for everything except for the specialized address approach.
        # We'll mimic "address is returned as 20 bytes" or a 32-later approach. 
        # For simplicity, let's store it as a 32 byte with the leading 20 bytes as the actual address.
        # But TS code just calls 'formatPrimative(...) -> toUint(value, 32)' if numeric. 
        # For addresses it directly returns the address as string in many places.
        # We'll store the address as a 32 byte hex: 12 leading 0 bytes + 20 bytes of address
        # or just return the checksummed address. 
        # The original TS code actually calls 'formatPrimative' -> but the 'address' path is separate.
        # We'll do a fallback approach: raise error or return the raw address?
        return Web3.to_bytes(hexstr=value)  # raw 20 bytes
    elif isinstance(value, bool) or isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        # numeric
        return to_uint(value, 32)
    else:
        raise ArbSdkError("Unsupported type for format_primitive()")


async def serialize_params(
    params: List[Any],
    address_to_index=lambda addr: -1,
) -> bytes:
    """
    Recursively parse a list of primitive or array-of-primitive items 
    and return a concatenated byte array according to the 
    Arbitrum "byte serialization" schema.

    :param params: The list of items to serialize (can be nested lists)
    :param address_to_index: A function that returns the address table index if any
    :return: The final byte array
    """
    formatted_parts: List[bytes] = []

    for param in params:
        if isinstance(param, list):
            # array
            array_length = len(param)
            # 1-byte length
            formatted_parts.append(to_uint(array_length, 1))

            # if first item is an address, we check if all are registered
            if array_length > 0 and is_address_type(param[0]):
                indices = []
                for addr in param:
                    idx = await address_to_index(addr)
                    indices.append(idx)

                if all(i > -1 for i in indices):
                    # all addresses are registered
                    formatted_parts.append(to_uint(1, 1))
                    # each is a 4-byte index
                    for idx in indices:
                        formatted_parts.append(to_uint(idx, 4))
                else:
                    # not all are registered
                    formatted_parts.append(to_uint(0, 1))
                    for addr in param:
                        formatted_parts.append(format_primitive(addr))
            else:
                # Non-address array items
                for item in param:
                    formatted_parts.append(format_primitive(item))
        else:
            # single item
            if is_address_type(param):
                # check if registered
                idx = await address_to_index(param)
                if idx > -1:
                    # 1 + 4 bytes
                    formatted_parts.append(to_uint(1, 1))
                    formatted_parts.append(to_uint(idx, 4))
                else:
                    formatted_parts.append(to_uint(0, 1))
                    formatted_parts.append(format_primitive(param))
            else:
                # numeric, bool, or big string
                formatted_parts.append(format_primitive(param))

    return b"".join(formatted_parts)
