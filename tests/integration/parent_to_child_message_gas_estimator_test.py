import pytest

from scripts.test_setup import setup_testing_env
from arbitrum_py.message.parent_to_child_message_gas_estimator import (
    ParentToChildMessageGasEstimator,
)
from tests.integration.custom_fee_token.mocha_extensions import (
    it_only_when_custom_gas_token,
    it_only_when_eth,
)
from tests.integration.test_helpers import skip_if_mainnet


@pytest.fixture(scope="function", autouse=True)
def skip_mainnet(request):
    check = skip_if_mainnet()
    check(request)


@it_only_when_eth
def test_estimate_submission_fee_returns_non_zero_for_eth_chain():
    """Test that estimateSubmissionFee returns non-zero value for ETH chain"""
    setup_state = setup_testing_env()
    parent_provider = setup_state["parentProvider"]
    child_provider = setup_state["childProvider"]

    gas_estimator = ParentToChildMessageGasEstimator(child_provider)
    submission_fee = gas_estimator.estimate_submission_fee(parent_provider, parent_provider.eth.gas_price, 123456)

    assert str(submission_fee) != str(0), "Submission fee should not be zero"


@it_only_when_custom_gas_token
def test_estimate_submission_fee_returns_zero_for_custom_gas_token_chain():
    """Test that estimateSubmissionFee returns zero for custom gas token chain"""
    setup_state = setup_testing_env()
    parent_provider = setup_state["parentProvider"]
    child_provider = setup_state["childProvider"]

    gas_estimator = ParentToChildMessageGasEstimator(child_provider)
    submission_fee = gas_estimator.estimate_submission_fee(parent_provider, parent_provider.eth.gas_price, 123456)

    assert str(submission_fee) == str(0), "Submission fee should be zero"
