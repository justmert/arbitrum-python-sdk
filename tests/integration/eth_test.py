import threading

from eth_account import Account
from web3 import Web3

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.message import ChildToParentMessageStatus
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider
from arbitrum_py.message.child_to_parent_message import ChildToParentMessage
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.message.parent_transaction import ParentTransactionReceipt
from arbitrum_py.utils.lib import (
    get_native_token_decimals,
    scale_from_18_decimals_to_native_token_decimals,
)
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    is_arbitrum_network_with_custom_fee_token,
)
from tests.integration.test_helpers import (
    fund_child_signer,
    fund_parent_signer,
    mine_until_stop,
)


def test_transfers_ether_on_child():
    setup_state = setup_testing_env()
    child_signer = setup_state.child_signer

    fund_child_signer(child_signer)

    random_address = Account.create().address
    amount_to_send = Web3.to_wei(0.000005, "ether")

    balance_before = child_signer.provider.eth.get_balance(child_signer.account.address)

    tx_hash = child_signer.provider.eth.send_transaction(
        {
            "from": child_signer.account.address,
            "to": random_address,
            "value": amount_to_send,
            "maxFeePerGas": 15000000000,
            "maxPriorityFeePerGas": 0,
        }
    )

    tx_receipt = child_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    balance_after = child_signer.provider.eth.get_balance(child_signer.account.address)
    random_balance_after = child_signer.provider.eth.get_balance(random_address)

    assert str(random_balance_after) == str(amount_to_send), "Random address balance after should match sent amount"

    expected_balance_after = balance_before - tx_receipt["gasUsed"] * tx_receipt["effectiveGasPrice"] - amount_to_send
    assert balance_after == expected_balance_after, "Child signer balance after should be correctly reduced"


def test_deposit_ether():
    setup_state = setup_testing_env()
    eth_bridger = setup_state.eth_bridger
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    parent_provider = parent_signer.provider
    child_chain = setup_state.child_chain

    decimals = get_native_token_decimals(parent_provider=parent_provider, child_network=child_chain)

    fund_parent_signer(parent_signer)
    inbox_address = eth_bridger.child_network.eth_bridge.inbox

    initial_inbox_balance = parent_signer.provider.eth.get_balance(inbox_address)
    amount = "0.0002"
    eth_to_deposit = Web3.to_wei(float(amount), "ether")

    rec = eth_bridger.deposit(
        {
            "amount": eth_to_deposit,
            "parentSigner": parent_signer,
        }
    )

    assert rec["status"] == 1, "ETH deposit parent transaction failed"
    final_inbox_balance = parent_signer.provider.eth.get_balance(inbox_address)

    # SEE PR: https://github.com/OffchainLabs/arbitrum-sdk/pull/567
    # assert final_inbox_balance == initial_inbox_balance + eth_to_deposit, "Balance failed to update after ETH deposit"

    wait_result = rec.wait_for_child_transaction_receipt(child_signer.provider)
    parent_to_child_messages = rec.get_eth_deposits(child_signer.provider)
    parent_to_child_message = parent_to_child_messages[0]

    assert len(parent_to_child_messages) == 1, "Failed to find 1 parent-to-child message"
    assert parent_to_child_message.to == parent_signer.account.address, "Message inputs value error"
    assert str(parent_to_child_message.value) == str(Web3.to_wei(float(amount), "ether")), "Message value error"

    assert wait_result["complete"], "ETH deposit not complete"
    assert wait_result["childTxReceipt"] is not None

    test_wallet_child_eth_balance = child_signer.provider.eth.get_balance(child_signer.account.address)
    assert str(test_wallet_child_eth_balance) == str(Web3.to_wei(float(amount), "ether")), "Final balance incorrect"


def test_deposits_ether_to_specific_child_address():
    setup_state = setup_testing_env()
    eth_bridger = setup_state.eth_bridger
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    parent_provider = parent_signer.provider
    child_chain = setup_state.child_chain

    decimals = get_native_token_decimals(parent_provider=parent_provider, child_network=child_chain)

    fund_parent_signer(parent_signer)

    inbox_address = eth_bridger.child_network.eth_bridge.inbox
    dest_wallet = Account.create()

    initial_inbox_balance = parent_signer.provider.eth.get_balance(inbox_address)

    amount = "0.0002"
    eth_to_deposit = Web3.to_wei(float(amount), "ether")

    rec = eth_bridger.deposit_to(
        {
            "amount": eth_to_deposit,
            "parentSigner": parent_signer,
            "destinationAddress": dest_wallet.address,
            "childProvider": child_signer.provider,
        }
    )

    assert rec["status"] == 1, "ETH deposit parent transaction failed"

    final_inbox_balance = parent_signer.provider.eth.get_balance(inbox_address)

    # SEE PR: https://github.com/OffchainLabs/arbitrum-sdk/pull/567
    # assert final_inbox_balance == initial_inbox_balance + eth_to_deposit, "Balance failed to update"

    parent_to_child_messages = rec.get_parent_to_child_messages(child_signer.provider)
    assert len(parent_to_child_messages) == 1, "Failed to find 1 parent-to-child message"
    parent_to_child_message = parent_to_child_messages[0]

    assert (
        parent_to_child_message.message_data["destAddress"] == dest_wallet.address
    ), "Message destination address mismatch"
    assert str(parent_to_child_message.message_data["l2CallValue"]) == str(
        Web3.to_wei(float(amount), "ether")
    ), "Message value error"

    retryable_ticket_result = parent_to_child_message.wait_for_status()
    assert retryable_ticket_result["status"] == ParentToChildMessageStatus.REDEEMED, "Retryable ticket not redeemed"

    retryable_tx_receipt = child_signer.provider.eth.get_transaction_receipt(
        parent_to_child_message.retryable_creation_id
    )
    assert retryable_tx_receipt is not None, "Retryable transaction receipt not found"

    child_retryable_tx_receipt = ChildTransactionReceipt(retryable_tx_receipt)
    ticket_redeem_events = child_retryable_tx_receipt.get_redeem_scheduled_events()

    assert len(ticket_redeem_events) == 1, "Failed finding the redeem event"
    assert ticket_redeem_events[0]["retryTxHash"] is not None, "Retry transaction hash not found"

    test_wallet_child_eth_balance = child_signer.provider.eth.get_balance(dest_wallet.address)
    assert str(test_wallet_child_eth_balance) == str(Web3.to_wei(float(amount), "ether")), "Final balance incorrect"


def test_deposit_ether_to_specific_child_address_with_manual_redeem():
    setup_state = setup_testing_env()
    eth_bridger = setup_state.eth_bridger
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    parent_provider = parent_signer.provider
    child_chain = setup_state.child_chain

    decimals = get_native_token_decimals(parent_provider=parent_provider, child_network=child_chain)

    fund_parent_signer(parent_signer)
    dest_wallet = Account.create()

    amount = "0.0002"
    eth_to_deposit = Web3.to_wei(float(amount), "ether")

    rec = eth_bridger.deposit_to(
        {
            "amount": eth_to_deposit,
            "parentSigner": parent_signer,
            "destinationAddress": dest_wallet.address,
            "childProvider": child_signer.provider,
            "retryableGasOverrides": {
                "gasLimit": {
                    "base": 0,  # causes auto-redeem to fail
                }
            },
        }
    )

    # rec = res.wait()
    parent_to_child_messages = rec.get_parent_to_child_messages(child_signer.provider)
    assert len(parent_to_child_messages) == 1, "Failed to find 1 parent-to-child message"
    parent_to_child_message_reader = parent_to_child_messages[0]

    retryable_ticket_result = parent_to_child_message_reader.wait_for_status()
    assert retryable_ticket_result["status"] == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD, "Unexpected status"

    test_wallet_child_eth_balance = child_signer.provider.eth.get_balance(dest_wallet.address)
    assert test_wallet_child_eth_balance == 0, "Balance before auto-redeem should be zero"

    fund_child_signer(child_signer)

    parent_tx_receipt = parent_signer.provider.eth.get_transaction_receipt(rec.transactionHash)

    parent_tx_receipt = ParentTransactionReceipt(parent_tx_receipt)
    parent_to_child_message_writer = parent_tx_receipt.get_parent_to_child_messages(child_signer)[0]

    parent_to_child_message_writer.redeem().wait()

    test_wallet_child_eth_balance = child_signer.provider.eth.get_balance(dest_wallet.address)
    assert str(test_wallet_child_eth_balance) == str(
        Web3.to_wei(float(amount), "ether")
    ), "Balance after manual redeem incorrect"


def test_withdraw_ether_transaction_succeeds():
    setup_state = setup_testing_env()
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain
    parent_signer = setup_state.parent_signer
    parent_provider = parent_signer.provider
    eth_bridger = setup_state.eth_bridger

    fund_child_signer(child_signer)
    fund_parent_signer(parent_signer)

    eth_to_withdraw = Web3.to_wei(0.00000002, "ether")
    random_address = Account.create().address

    request = eth_bridger.get_withdrawal_request(
        {
            "amount": eth_to_withdraw,
            "destinationAddress": random_address,
            "from": child_signer.account.address,
        }
    )

    parent_gas_estimate = request["estimateParentGasLimit"](parent_signer.provider)

    withdraw_eth_rec = eth_bridger.withdraw(
        {
            "amount": eth_to_withdraw,
            "childSigner": child_signer,
            "destinationAddress": random_address,
            "from": child_signer.account.address,
        }
    )

    # withdraw_eth_rec = withdraw_eth_res.wait()
    assert withdraw_eth_rec["status"] == 1, "Initiate ETH withdraw transaction failed"

    withdraw_message = withdraw_eth_rec.get_child_to_parent_messages(parent_signer)[0]
    assert withdraw_message is not None, "ETH withdraw query empty"

    withdraw_events = ChildToParentMessage.get_child_to_parent_events(
        child_signer.provider,
        {"fromBlock": withdraw_eth_rec["blockNumber"], "toBlock": "latest"},
        None,
        random_address,
    )
    assert len(withdraw_events) == 1, "ETH withdraw event data failed"

    message_status = withdraw_message.status(child_signer.provider)
    assert message_status == ChildToParentMessageStatus.UNCONFIRMED, f"Wrong status: {message_status}"

    # Set up mining threads
    miner1_seed = Account.create()
    miner2_seed = Account.create()

    miner1_private_key = miner1_seed.key.hex()
    miner2_private_key = miner2_seed.key.hex()

    miner1_account = Account.from_key(miner1_private_key)
    miner2_account = Account.from_key(miner2_private_key)

    miner1 = SignerOrProvider(miner1_account, parent_signer.provider)
    miner2 = SignerOrProvider(miner2_account, child_signer.provider)
    fund_parent_signer(miner1, Web3.to_wei(1, "ether"))
    fund_child_signer(miner2, Web3.to_wei(1, "ether"))

    state = {"mining": True}
    miner1_thread = threading.Thread(target=mine_until_stop, args=(miner1, state))
    miner2_thread = threading.Thread(target=mine_until_stop, args=(miner2, state))
    message_thread = threading.Thread(
        target=lambda: withdraw_message.wait_until_ready_to_execute(child_signer.provider)
    )

    miner1_thread.daemon = True
    miner2_thread.daemon = True
    message_thread.daemon = True

    miner1_thread.start()
    miner2_thread.start()
    message_thread.start()

    message_thread.join()
    state["mining"] = False

    assert withdraw_message.status(child_signer.provider) == ChildToParentMessageStatus.CONFIRMED

    exec_rec = withdraw_message.execute(child_signer.provider)

    assert exec_rec["gasUsed"] < parent_gas_estimate, "Gas used greater than estimate"
    assert withdraw_message.status(child_signer.provider) == ChildToParentMessageStatus.EXECUTED

    decimals = get_native_token_decimals(parent_provider=parent_provider, child_network=child_chain)

    if is_arbitrum_network_with_custom_fee_token():
        final_random_balance = (
            eth_bridger.get_parent_token_contract(parent_signer.provider, eth_bridger.native_token)
            .functions.balanceOf(random_address)
            .call()
        )
    else:
        final_random_balance = parent_signer.provider.eth.get_balance(random_address)

    expected_balance = scale_from_18_decimals_to_native_token_decimals(amount=eth_to_withdraw, decimals=decimals)
    assert str(final_random_balance) == str(expected_balance), "Parent chain final balance incorrect"
