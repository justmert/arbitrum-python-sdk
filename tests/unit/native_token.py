import pytest
from decimal import Decimal

from web3 import Web3

from arbitrum_py.utils.lib import (
    scale_from_18_decimals_to_native_token_decimals,
    scale_from_native_token_decimals_to_18_decimals,
)

# Equivalent to parseEther('1.23456789')
AMOUNT_TO_SCALE = Web3.to_wei(Decimal("1.23456789"), "ether")


def decimals_to_error(decimals: int) -> str:
    """Helper function to format error message"""
    return f"incorrect scaling result for {decimals} decimals"


class TestNativeToken:
    def test_scales_to_native_token_decimals(self):
        """Test scaling to native token decimals with various decimal places"""

        # Test 18 decimals - no rounding
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=18)
        assert result == 1234567890000000000, decimals_to_error(18)

        # Test 0 decimals - rounds up 1 to 2
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=0)
        assert result == 2, decimals_to_error(0)

        # Test 1 decimal - rounds up
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=1)
        assert result == 13, decimals_to_error(1)

        # Test 6 decimals - rounds up
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=6)
        assert result == 1234568, decimals_to_error(6)

        # Test 7 decimals - rounds up
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=7)
        assert result == 12345679, decimals_to_error(7)

        # Test 8 decimals - no rounding (all original decimals included)
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=8)
        assert result == 123456789, decimals_to_error(8)

        # Test 9 decimals - no rounding (all original decimals included)
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=9)
        assert result == 1234567890, decimals_to_error(9)

        # Test 24 decimals - no rounding (all original decimals included)
        result = scale_from_18_decimals_to_native_token_decimals(amount=AMOUNT_TO_SCALE, decimals=24)
        assert result == 1234567890000000000000000, decimals_to_error(24)

    def test_scales_native_token_decimals_to_18_decimals(self):
        """Test scaling from native token decimals to 18 decimals"""

        # Test 16 decimals
        result = scale_from_native_token_decimals_to_18_decimals(amount=AMOUNT_TO_SCALE, decimals=16)
        assert result == 123456789000000000000, decimals_to_error(16)

        # Test 18 decimals
        result = scale_from_native_token_decimals_to_18_decimals(amount=AMOUNT_TO_SCALE, decimals=18)
        assert result == 1234567890000000000, decimals_to_error(18)

        # Test 20 decimals
        result = scale_from_native_token_decimals_to_18_decimals(amount=AMOUNT_TO_SCALE, decimals=20)
        assert result == 12345678900000000, decimals_to_error(20)
