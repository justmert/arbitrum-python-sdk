from web3 import Web3
import pytest
from arbitrum_py.data_entities.address import Address
from arbitrum_py.data_entities.constants import ADDRESS_ALIAS_OFFSET

ADDRESS_ALIAS_OFFSET_INT = int(ADDRESS_ALIAS_OFFSET, 16)
MAX_ADDR_INT = 2**160 - 1


def apply_undo_test(addr, expected_apply, expected_undo):
    address = Address(addr)

    after_apply = address.apply_alias()
    assert after_apply.value == expected_apply

    after_apply_undo = after_apply.undo_alias()
    assert after_apply_undo.value == addr

    after_undo = address.undo_alias()
    assert after_undo.value == expected_undo

    after_undo_apply = after_undo.apply_alias()
    assert after_undo_apply.value == addr


def test_alias_below_offset():
    below_offset_int = (MAX_ADDR_INT - ADDRESS_ALIAS_OFFSET_INT - 10) & MAX_ADDR_INT
    below_offset_hex = Web3.to_hex(below_offset_int)

    apply_undo_test(
        Web3.to_checksum_address(below_offset_hex),
        Web3.to_checksum_address("0xfffffffffffffffffffffffffffffffffffffff5"),
        Web3.to_checksum_address("0xddddffffffffffffffffffffffffffffffffddd3"),
    )


def test_alias_on_offset():
    on_offset_int = (MAX_ADDR_INT - ADDRESS_ALIAS_OFFSET_INT) & MAX_ADDR_INT
    on_offset_hex = Web3.to_hex(on_offset_int)

    apply_undo_test(
        Web3.to_checksum_address(on_offset_hex),
        Web3.to_checksum_address("0xffffffffffffffffffffffffffffffffffffffff"),
        Web3.to_checksum_address("0xddddffffffffffffffffffffffffffffffffdddd"),
    )


def test_alias_above_offset():
    above_offset_int = (MAX_ADDR_INT - ADDRESS_ALIAS_OFFSET_INT + 10) & MAX_ADDR_INT
    above_offset_hex = Web3.to_hex(above_offset_int)

    apply_undo_test(
        Web3.to_checksum_address(above_offset_hex),
        Web3.to_checksum_address("0x0000000000000000000000000000000000000009"),
        Web3.to_checksum_address("0xddddffffffffffffffffffffffffffffffffdde7"),
    )


def test_alias_special_case():
    special = "0xFfC98231ef2fd1F77106E10581A1faC14E29d014"
    apply_undo_test(
        Web3.to_checksum_address(special),
        Web3.to_checksum_address("0x10da8231ef2fd1f77106e10581a1fac14e29e125"),
        Web3.to_checksum_address("0xeeb88231ef2fd1f77106e10581a1fac14e29bf03"),
    )
