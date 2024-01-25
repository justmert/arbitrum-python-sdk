from eth_account import Account
import pytest
from web3 import Web3
# Import other necessary modules and set up fixtures
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.message.l1_to_l2_message_creator import L1ToL2MessageCreator
from .test_helpers import (
    fund_l1,
    fund_l2,
)
from src.scripts.test_setup import test_setup


# Assuming testAmount is defined globally
TEST_AMOUNT = Web3.to_wei('0.01', 'ether')

@pytest.fixture
async def setup_state():
    setup = await test_setup()
    return setup


@pytest.mark.asyncio
async def test_retryable_ticket_creation_with_parameters(setup_state):
    l1_signer, l2_signer = setup_state['l1_signer'], setup_state['l2_signer']
    
    # Assuming fund_l1 is a function to fund the L1 wallet
    fund_l1(l1_signer)

    # Instantiate the L1ToL2MessageCreator object
    # Implement L1ToL2MessageCreator class in Python
    l1_to_l2_message_creator = L1ToL2MessageCreator(l1_signer)

    # Getting initial L2 balance
    initial_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)


    # Define parameters for Retryable Ticket
    retryable_ticket_params = {
        'from': l1_signer.account.address,
        'to': l1_signer.account.address,
        'l2CallValue': TEST_AMOUNT,
        'callValueRefundAddress': l1_signer.account.address,
        'data': '0x',
    }

    # Submitting the ticket
    l1_submission_tx_receipt = await l1_to_l2_message_creator.create_retryable_ticket(
        retryable_ticket_params, l2_signer.provider
    )
    print("l1_submission_tx_receipt", l1_submission_tx_receipt)
    # l1_submission_tx_receipt = l1_submission_tx.wait()

    # Getting the L1ToL2Message and checking status
    l1_to_l2_messages = await l1_submission_tx_receipt.get_l1_to_l2_messages(l2_signer.provider)
    print('*-*******l1_to_l2_messages', l1_to_l2_messages)
    assert len(l1_to_l2_messages) == 1
    l1_to_l2_message = l1_to_l2_messages[0]


    # Wait for it to be redeemed
    print('waiting for status')
    retryable_ticket_result = await l1_to_l2_message.wait_for_status()
    assert retryable_ticket_result['status'] == L1ToL2MessageStatus.REDEEMED

    # Checking updated balances
    # final_l2_balance = await l2_signer.account.get_balance()
    final_l2_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    assert initial_l2_balance + TEST_AMOUNT < final_l2_balance


# @pytest.mark.asyncio
# async def test_retryable_ticket_creation_with_request(setup_state):
#     l1_signer, l2_signer = setup_state['l1_signer'], setup_state['l2_signer']

#     fund_l1(l1_signer)

#     l1_to_l2_message_creator = L1ToL2MessageCreator(l1_signer)

#     initial_l2_balance = await l2_signer.account.balance

#     l1_to_l2_transaction_request_params = {
#         'from': l1_signer.address,
#         'to': l1_signer.address,
#         'l2CallValue': TEST_AMOUNT,
#         'callValueRefundAddress': l1_signer.address,
#         'data': '0x',
#     }

#     l1_to_l2_transaction_request = await L1ToL2MessageCreator.get_ticket_creation_request(
#         l1_to_l2_transaction_request_params, l1_signer.provider, l2_signer.provider
#     )

#     l1_submission_tx = await l1_to_l2_message_creator.create_retryable_ticket(
#         l1_to_l2_transaction_request, l2_signer.provider
#     )
#     l1_submission_tx_receipt = await l1_submission_tx.wait()

#     l1_to_l2_messages = await l1_submission_tx_receipt.get_l1_to_l2_messages(l2_signer.provider)
#     assert len(l1_to_l2_messages) == 1
#     l1_to_l2_message = l1_to_l2_messages[0]

#     retryable_ticket_result = await l1_to_l2_message.wait_for_status()
#     assert retryable_ticket_result.status == L1ToL2MessageStatus.REDEEMED

#     final_l2_balance = await l2_signer.account.balance
#     assert initial_l2_balance + TEST_AMOUNT < final_l2_balance

