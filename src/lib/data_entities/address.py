from web3 import Web3

from src.lib.data_entities.constants import ADDRESS_ALIAS_OFFSET
from src.lib.data_entities.errors import ArbSdkError

class Address:
    """
    Represents an Ethereum/Arbitrum address, with support for applying 
    and undoing the L1 <-> L2 alias offset used on Arbitrum.
    """

    # Convert the address alias offset from hex string to an integer, e.g. "0x11110000..." -> int
    ADDRESS_ALIAS_OFFSET_BIG_INT = int(ADDRESS_ALIAS_OFFSET, 16)
    ADDRESS_BIT_LENGTH = 160  # For standard Ethereum addresses
    ADDRESS_NIBBLE_LENGTH = ADDRESS_BIT_LENGTH // 4  # 160 bits => 40 hex chars

    def __init__(self, value: str):
        """
        :param value: A string representing a valid Ethereum address (case-insensitive).
        :raises ArbSdkError: If 'value' is not a valid address according to web3 checks.
        """
        if not Web3.is_address(value):
            raise ArbSdkError(f"'{value}' is not a valid address")
        self.value = Web3.to_checksum_address(value)

    def _alias(self, address: str, forward: bool) -> str:
        """
        Internal helper to compute the address alias by adding or subtracting ADDRESS_ALIAS_OFFSET.
        Under the hood, we ensure the result fits in 160 bits.

        :param address: A valid checksummed or hex Ethereum address as a string (no '0x' prefix stripped).
        :param forward: If True, add the alias offset (computing L1->L2 alias). 
                        If False, subtract it (computing L2->L1).
        :return: The checksummed aliased address as a string.
        """
        address_int = int(address, 16)
        if forward:
            offset_int = address_int + self.ADDRESS_ALIAS_OFFSET_BIG_INT
        else:
            offset_int = address_int - self.ADDRESS_ALIAS_OFFSET_BIG_INT

        # Restrict to 160 bits. 
        # (1 << 160) - 1 is a bitmask with 160 ones in binary.
        mod_address_int = offset_int & ((1 << self.ADDRESS_BIT_LENGTH) - 1)

        # Convert to hex (without '0x'), zero-pad to 40 hex digits
        aliased_hex_str = hex(mod_address_int)[2:].zfill(self.ADDRESS_NIBBLE_LENGTH)
        # Convert to fully checksummed address
        return Web3.to_checksum_address("0x" + aliased_hex_str)

    def apply_alias(self) -> "Address":
        """
        Computes the L2 alias for an L1 address by adding the offset.

        :return: A new Address object that is the L2 alias of this address.
        """
        return Address(self._alias(self.value[2:], forward=True))

    def undo_alias(self) -> "Address":
        """
        Computes the L1 address for an L2 alias by subtracting the offset.

        :return: A new Address object that is the L1 version of this aliased address.
        """
        return Address(self._alias(self.value[2:], forward=False))

    def equals(self, other: "Address") -> bool:
        """
        Compare two addresses in a case-insensitive way.

        :param other: Another Address object
        :return: True if both addresses match (ignoring case), else False
        """
        return self.value.lower() == other.value.lower()
