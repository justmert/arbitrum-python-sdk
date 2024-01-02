from web3 import Web3
from web3.auto import w3
from eth_typing import HexStr
from typing import Union, List, Callable
from eth_utils import to_checksum_address, is_address, big_endian_to_int, int_to_big_endian
from src.lib.data_entities.errors import ArbSdkError

def is_address_type(input_value: Union[int, str, bool]):
    return isinstance(input_value, str) and is_address(input_value)

def to_uint(val: Union[int, str, bool], bytes_size: int) -> bytes:
    if isinstance(val, bool):
        val = 1 if val else 0
    return int_to_big_endian(int(val)).rjust(bytes_size, b'\0')

def format_primitive(value: Union[int, str, bool]) -> HexStr:
    if is_address_type(value):
        return to_checksum_address(value)
    elif isinstance(value, bool) or isinstance(value, int) or isinstance(value, str):
        return Web3.to_hex(to_uint(value, 32))
    else:
        raise ArbSdkError('Unsupported type')

async def serialize_params(params: List[Union[int, str, bool, List[Union[int, str, bool]]]],
                           address_to_index: Callable[[str], int] = lambda x: -1) -> bytes:
    formatted_params = []

    for param in params:
        if isinstance(param, list):
            formatted_params.append(to_uint(len(param), 1))
            if is_address_type(param[0]):
                indices = [await address_to_index(addr) for addr in param]
                if all(i > -1 for i in indices):
                    formatted_params.append(to_uint(1, 1))
                    formatted_params.extend([to_uint(i, 4) for i in indices])
                else:
                    formatted_params.append(to_uint(0, 1))
                    formatted_params.extend([format_primitive(addr) for addr in param])
            else:
                formatted_params.extend([format_primitive(item) for item in param])
        else:
            if is_address_type(param):
                index = await address_to_index(param)
                if index > -1:
                    formatted_params.extend([to_uint(1, 1), to_uint(index, 4)])
                else:
                    formatted_params.extend([to_uint(0, 1), format_primitive(param)])
            else:
                formatted_params.append(format_primitive(param))

    return b''.join(formatted_params)