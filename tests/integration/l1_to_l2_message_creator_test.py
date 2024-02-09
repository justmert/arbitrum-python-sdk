import pytest
from web3 import Web3

from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.message.l1_to_l2_message_creator import L1ToL2MessageCreator
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import (
    fund_l1,
)

TEST_AMOUNT = Web3.to_wei("0.01", "ether")


@pytest.fixture(scope="function")
async def setup_state():
    setup = await test_setup()
    return setup


@pytest.fixture(scope="function", autouse=True)
async def skip_if_mainnet(request, setup_state):
    chain_id = setup_state.l1_network.chain_id
    if chain_id == 1:
        pytest.skip("Skipping test on mainnet")


@pytest.mark.asyncio
async def test_retryable_ticket_creation_with_parameters(setup_state):
    l1_signer, l2_signer = setup_state.l1_signer, setup_state.l2_signer
    signer_address = l1_signer.account.address
    arb_provider = l2_signer.provider

    fund_l1(l1_signer)

    l1_to_l2_message_creator = L1ToL2MessageCreator(l1_signer)

    initial_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)

    retryable_ticket_params = {
        "from": signer_address,
        "to": signer_address,
        "l2CallValue": TEST_AMOUNT,
        "callValueRefundAddress": signer_address,
        "data": "0x",
    }

    l1_submission_tx_receipt = await l1_to_l2_message_creator.create_retryable_ticket(
        retryable_ticket_params, arb_provider
    )

    l1_to_l2_messages = await l1_submission_tx_receipt.get_l1_to_l2_messages(arb_provider)

    assert len(l1_to_l2_messages) == 1
    l1_to_l2_message = l1_to_l2_messages[0]

    retryable_ticket_result = await l1_to_l2_message.wait_for_status()
    assert retryable_ticket_result["status"] == L1ToL2MessageStatus.REDEEMED
    final_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    assert initial_l2_balance + TEST_AMOUNT < final_l2_balance


@pytest.mark.asyncio
async def test_retryable_ticket_creation_with_request(setup_state):
    l1_signer, l2_signer = setup_state.l1_signer, setup_state.l2_signer
    signer_address = l1_signer.account.address
    eth_provider = l1_signer.provider
    arb_provider = l2_signer.provider

    fund_l1(l1_signer)

    l1_to_l2_message_creator = L1ToL2MessageCreator(l1_signer)

    initial_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)

    l1_to_l2_transaction_request_params = {
        "from": signer_address,
        "to": signer_address,
        "l2CallValue": TEST_AMOUNT,
        "callValueRefundAddress": signer_address,
        "data": "0x",
    }

    l1_to_l2_transaction_request = await L1ToL2MessageCreator.get_ticket_creation_request(
        l1_to_l2_transaction_request_params, eth_provider, arb_provider
    )

    l1_submission_tx_receipt = await l1_to_l2_message_creator.create_retryable_ticket(
        l1_to_l2_transaction_request, arb_provider
    )

    l1_to_l2_messages = await l1_submission_tx_receipt.get_l1_to_l2_messages(arb_provider)
    assert len(l1_to_l2_messages) == 1
    l1_to_l2_message = l1_to_l2_messages[0]

    retryable_ticket_result = await l1_to_l2_message.wait_for_status()
    assert retryable_ticket_result["status"] == L1ToL2MessageStatus.REDEEMED

    final_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    assert initial_l2_balance + TEST_AMOUNT < final_l2_balance
