import pytest
from web3 import Web3

from scripts.test_setup import setup_testing_env
from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.message.parent_to_child_message_creator import ParentToChildMessageCreator
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    approve_parent_custom_fee_token,
    fund_parent_custom_fee_token,
    is_arbitrum_network_with_custom_fee_token,
)
from tests.integration.test_helpers import fund_parent_signer, skip_if_mainnet

TEST_AMOUNT = Web3.to_wei("0.01", "ether")


@pytest.fixture(scope="function")
def setup_state():
    return setup_testing_env()


@pytest.fixture(scope="function", autouse=True)
def skip_mainnet(request):
    check = skip_if_mainnet()
    check(request)


def test_retryable_ticket_creation_with_parameters(setup_state):
    parent_signer = setup_state["parentSigner"]
    child_signer = setup_state["childSigner"]
    signer_address = parent_signer.account.address
    arb_provider = child_signer.provider

    # Fund parent chain wallet
    fund_parent_signer(parent_signer)

    # Handle custom fee token if necessary
    if is_arbitrum_network_with_custom_fee_token():
        fund_parent_custom_fee_token(parent_signer)
        approve_parent_custom_fee_token(parent_signer)

    parent_to_child_message_creator = ParentToChildMessageCreator(parent_signer)

    initial_child_chain_balance = child_signer.provider.eth.get_balance(child_signer.account.address)

    retryable_ticket_params = {
        "from": signer_address,
        "to": signer_address,
        "l2CallValue": TEST_AMOUNT,
        "callValueRefundAddress": signer_address,
        "data": "0x",
    }

    parent_submission_tx_receipt = parent_to_child_message_creator.create_retryable_ticket(
        retryable_ticket_params, arb_provider
    )

    parent_to_child_messages = parent_submission_tx_receipt.get_parent_to_child_messages(arb_provider)

    assert len(parent_to_child_messages) == 1
    parent_to_child_message = parent_to_child_messages[0]

    retryable_ticket_result = parent_to_child_message.wait_for_status()
    assert retryable_ticket_result["status"] == ParentToChildMessageStatus.REDEEMED

    final_child_chain_balance = child_signer.provider.eth.get_balance(child_signer.account.address)
    assert initial_child_chain_balance + TEST_AMOUNT < final_child_chain_balance, "Child chain balance not updated"


def test_retryable_ticket_creation_with_request(setup_state):
    parent_signer = setup_state["parentSigner"]
    child_signer = setup_state["childSigner"]
    signer_address = parent_signer.account.address
    eth_provider = parent_signer.provider
    arb_provider = child_signer.provider

    # Fund parent chain wallet
    fund_parent_signer(parent_signer)

    # Handle custom fee token if necessary
    if is_arbitrum_network_with_custom_fee_token():
        fund_parent_custom_fee_token(parent_signer)
        approve_parent_custom_fee_token(parent_signer)

    parent_to_child_message_creator = ParentToChildMessageCreator(parent_signer)

    initial_child_chain_balance = child_signer.provider.eth.get_balance(child_signer.account.address)

    parent_to_child_transaction_request_params = {
        "from": signer_address,
        "to": signer_address,
        "l2CallValue": TEST_AMOUNT,
        "callValueRefundAddress": signer_address,
        "data": "0x",
    }

    parent_to_child_transaction_request = ParentToChildMessageCreator.get_ticket_creation_request(
        parent_to_child_transaction_request_params, eth_provider, arb_provider
    )

    parent_submission_tx_receipt = parent_to_child_message_creator.create_retryable_ticket(
        parent_to_child_transaction_request, arb_provider
    )

    parent_to_child_messages = parent_submission_tx_receipt.get_parent_to_child_messages(arb_provider)
    assert len(parent_to_child_messages) == 1
    parent_to_child_message = parent_to_child_messages[0]

    retryable_ticket_result = parent_to_child_message.wait_for_status()
    assert retryable_ticket_result["status"] == ParentToChildMessageStatus.REDEEMED

    final_child_chain_balance = child_signer.provider.eth.get_balance(child_signer.account.address)
    assert initial_child_chain_balance + TEST_AMOUNT < final_child_chain_balance, "Child chain balance not updated"
