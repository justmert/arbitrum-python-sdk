import pytest

from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    is_arbitrum_network_with_custom_fee_token,
)

# Cache the environment check
custom_gas_token_environment = is_arbitrum_network_with_custom_fee_token()


def describe_only_when_eth(fn):
    """
    Decorator to skip test class when in custom gas token environment
    Only run when in an eth chain environment
    """
    return pytest.mark.skipif(custom_gas_token_environment, reason="Test only runs in ETH chain environment")(fn)


def describe_only_when_custom_gas_token(fn):
    """
    Decorator to skip test class when in eth environment
    Only run when in a custom gas token chain environment
    """
    return pytest.mark.skipif(
        not custom_gas_token_environment, reason="Test only runs in custom gas token environment"
    )(fn)


def it_only_when_eth(fn):
    """
    Decorator to skip individual test when in custom gas token environment
    Only run when in an eth chain environment
    """
    return pytest.mark.skipif(custom_gas_token_environment, reason="Test only runs in ETH chain environment")(fn)


def it_only_when_custom_gas_token(fn):
    """
    Decorator to skip individual test when in eth environment
    Only run when in a custom gas token chain environment
    """
    return pytest.mark.skipif(
        not custom_gas_token_environment, reason="Test only runs in custom gas token environment"
    )(fn)
