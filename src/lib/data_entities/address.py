from web3 import Web3

from src.lib.data_entities.constants import ADDRESS_ALIAS_OFFSET
from src.lib.data_entities.errors import ArbSdkError


class Address:
    ADDRESS_ALIAS_OFFSET_BIG_INT = int(ADDRESS_ALIAS_OFFSET, 16)
    ADDRESS_BIT_LENGTH = 160
    ADDRESS_NIBBLE_LENGTH = ADDRESS_BIT_LENGTH // 4

    def __init__(self, value):
        if not Web3.is_address(value):
            raise ArbSdkError(f"'{value}' is not a valid address")
        self.value = value

    def alias(self, address, forward):
        address_int = int(address, 16)
        if forward:
            offset = address_int + self.ADDRESS_ALIAS_OFFSET_BIG_INT
        else:
            offset = address_int - self.ADDRESS_ALIAS_OFFSET_BIG_INT
        aliased_address = hex(offset & ((1 << self.ADDRESS_BIT_LENGTH) - 1))[2:]
        padded_address = aliased_address.zfill(self.ADDRESS_NIBBLE_LENGTH)
        return Web3.to_checksum_address("0x" + padded_address)

    def apply_alias(self):
        return Address(self.alias(self.value, True))

    def undo_alias(self):
        return Address(self.alias(self.value, False))

    def equals(self, other):
        return self.value.lower() == other.value.lower()
