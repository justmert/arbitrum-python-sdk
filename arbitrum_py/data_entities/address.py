from typing import Union

from web3 import Web3
from web3.types import ChecksumAddress

from arbitrum_py.data_entities.constants import ADDRESS_ALIAS_OFFSET
from arbitrum_py.data_entities.errors import ArbSdkError


class Address:
    """Ethereum/Arbitrum address class with L1/L2 aliasing support.

    This class represents an Ethereum/Arbitrum address and provides functionality
    for handling the L1 <-> L2 address aliasing used by Arbitrum. It ensures
    addresses are properly checksummed and validates their format.

    The aliasing system is used by Arbitrum to prevent address collisions between
    L1 and L2. When a contract on L1 sends a message to L2, its address is aliased
    by adding a constant offset. When L2 sends a message back to L1, the address
    is un-aliased by subtracting the same offset.

    Attributes:
        value (ChecksumAddress): The checksummed Ethereum address
        ADDRESS_ALIAS_OFFSET_BIG_INT (int): The numerical offset used for address aliasing
        ADDRESS_BIT_LENGTH (int): Number of bits in an Ethereum address (160)
        ADDRESS_NIBBLE_LENGTH (int): Number of hex characters needed (40)
    """

    # Convert the address alias offset from hex string to an integer
    ADDRESS_ALIAS_OFFSET_BIG_INT = int(ADDRESS_ALIAS_OFFSET, 16)
    ADDRESS_BIT_LENGTH = 160  # Standard Ethereum address length in bits
    ADDRESS_NIBBLE_LENGTH = ADDRESS_BIT_LENGTH // 4  # 160 bits = 40 hex chars

    def __init__(self, value: Union[str, ChecksumAddress]) -> None:
        """Initialize an Address instance with validation.

        Args:
            value: An Ethereum address. Can be checksummed or not, but must be valid.

        Raises:
            ArbSdkError: If the provided address is not a valid Ethereum address.
        """
        if not Web3.is_address(value):
            raise ArbSdkError(f"'{value}' is not a valid Ethereum address")
        self.value: ChecksumAddress = Web3.to_checksum_address(value)

    def _alias(self, address: str, forward: bool) -> ChecksumAddress:
        """Compute address alias by adding or subtracting the alias offset.

        Internal helper that performs the actual address aliasing computation.
        The result is guaranteed to fit within 160 bits through modular arithmetic.

        Args:
            address: A hex Ethereum address without '0x' prefix
            forward: If True, compute L1->L2 alias (add offset)
                    If False, compute L2->L1 alias (subtract offset)

        Returns:
            The checksummed aliased address
        """
        address_int = int(address, 16)
        if forward:
            offset_int = address_int + self.ADDRESS_ALIAS_OFFSET_BIG_INT
        else:
            offset_int = address_int - self.ADDRESS_ALIAS_OFFSET_BIG_INT

        # Ensure result fits in 160 bits using bitwise AND with mask
        mod_address_int = offset_int & ((1 << self.ADDRESS_BIT_LENGTH) - 1)

        # Convert to properly formatted address
        aliased_hex = hex(mod_address_int)[2:].zfill(self.ADDRESS_NIBBLE_LENGTH)
        return Web3.to_checksum_address("0x" + aliased_hex)

    def apply_alias(self) -> "Address":
        """Compute the L2 alias of this L1 address.

        When contracts on L1 send messages to L2, their addresses are aliased
        by adding ADDRESS_ALIAS_OFFSET to prevent address collisions.

        Returns:
            A new Address instance representing the L2 alias of this address
        """
        return Address(self._alias(self.value[2:], forward=True))

    def undo_alias(self) -> "Address":
        """Compute the L1 address from this L2 alias.

        When contracts on L2 send messages back to L1, aliased addresses are
        converted back to their original L1 form by subtracting ADDRESS_ALIAS_OFFSET.

        Returns:
            A new Address instance representing the original L1 address
        """
        return Address(self._alias(self.value[2:], forward=False))

    def equals(self, other: "Address") -> bool:
        """Compare two addresses for equality, ignoring case.

        Args:
            other: Another Address instance to compare with

        Returns:
            True if the addresses match (case-insensitive), False otherwise
        """
        return self.value.lower() == other.value.lower()

    def __eq__(self, other: object) -> bool:
        """Enable == operator for comparing Address instances.

        Args:
            other: Object to compare with this Address

        Returns:
            True if other is an Address with the same value (case-insensitive)
        """
        if not isinstance(other, Address):
            return NotImplemented
        return self.equals(other)

    def __str__(self) -> str:
        """Get string representation of the address.

        Returns:
            The checksummed address value
        """
        return self.value

    def __repr__(self) -> str:
        """Get detailed string representation of the Address instance.

        Returns:
            A string showing the class name and checksummed address value
        """
        return f"Address('{self.value}')"
