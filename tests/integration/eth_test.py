import asyncio

import pytest
from eth_account import Account
from web3 import Web3

from src.lib.data_entities.message import L2ToL1MessageStatus
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import fund_l1, fund_l2, mine_until_stop


@pytest.mark.asyncio
async def test_transfers_ether_on_l2():
    setup_state = await test_setup()
    l2_signer = setup_state.l2_signer

    fund_l2(l2_signer)

    random_address = Account.create().address
    amount_to_send = Web3.to_wei(0.000005, "ether")

    balance_before = l2_signer.provider.eth.get_balance(l2_signer.account.address)

    tx_hash = l2_signer.provider.eth.send_transaction(
        {
            "from": l2_signer.account.address,
            "to": random_address,
            "value": amount_to_send,
            "maxFeePerGas": 15000000000,
            "maxPriorityFeePerGas": 0,
        }
    )

    tx_receipt = l2_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    balance_after = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    random_balance_after = l2_signer.provider.eth.get_balance(random_address)

    assert Web3.from_wei(random_balance_after, "ether") == Web3.from_wei(
        amount_to_send, "ether"
    ), "Random address balance after should match the sent amount"

    expected_balance_after = balance_before - tx_receipt.gasUsed * tx_receipt.effectiveGasPrice - amount_to_send

    assert balance_after == expected_balance_after, "L2 signer balance after should be correctly reduced"


@pytest.mark.asyncio
async def test_deposits_ether():
    setup_state = await test_setup()
    eth_bridger = setup_state.eth_bridger
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    initial_test_wallet_l2_eth_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)

    fund_l1(l1_signer)

    inbox_address = eth_bridger.l2_network.eth_bridge.inbox
    initial_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)

    eth_to_deposit = Web3.to_wei(0.0002, "ether")

    rec = await eth_bridger.deposit(
        {
            "amount": eth_to_deposit,
            "l1Signer": l1_signer,
        }
    )

    assert rec.status == 1, "ETH deposit L1 transaction failed"

    final_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)

    # Also fails in TS implementation - https://github.com/OffchainLabs/arbitrum-sdk/pull/407
    # assert final_inbox_balance == initial_inbox_balance + eth_to_deposit, "Balance failed to update after ETH deposit"

    wait_result = await rec.wait_for_l2(l2_signer.provider)

    l1_to_l2_messages = await rec.get_eth_deposits(l2_signer.provider)

    assert len(l1_to_l2_messages) == 1, "Failed to find 1 L1 to L2 message"
    l1_to_l2_message = l1_to_l2_messages[0]

    wallet_address = l1_signer.account.address

    assert l1_to_l2_message.to_address == wallet_address, "Message inputs value error"

    assert l1_to_l2_message.value == eth_to_deposit, "Message inputs value error"

    assert wait_result["complete"], "Eth deposit not complete"
    assert wait_result["l2TxReceipt"] is not None

    final_test_wallet_l2_eth_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    assert (
        final_test_wallet_l2_eth_balance == initial_test_wallet_l2_eth_balance + eth_to_deposit
    ), "Final balance incorrect"


@pytest.mark.asyncio
async def test_deposits_ether_to_specific_l2_address():
    setup_state = await test_setup()
    eth_bridger = setup_state.eth_bridger
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer

    fund_l1(l1_signer)

    inbox_address = eth_bridger.l2_network.eth_bridge.inbox
    initial_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)

    dest_wallet = Account.create()

    eth_to_deposit = Web3.to_wei(0.0002, "ether")
    rec = await eth_bridger.deposit_to(
        {
            "amount": eth_to_deposit,
            "l1Signer": l1_signer,
            "destinationAddress": dest_wallet.address,
            "l2Provider": l2_signer.provider,
        }
    )

    assert rec.status == 1, "ETH deposit L1 transaction failed"

    final_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)

    # Also fails in TS implementation - https://github.com/OffchainLabs/arbitrum-sdk/pull/407
    # assert final_inbox_balance == initial_inbox_balance + eth_to_deposit, "Balance failed to update after ETH deposit"

    l1_to_l2_messages = await rec.get_l1_to_l2_messages(l2_signer.provider)
    assert len(l1_to_l2_messages) == 1, "Failed to find 1 L1 to L2 message"
    l1_to_l2_message = l1_to_l2_messages[0]

    assert l1_to_l2_message.message_data["destAddress"] == dest_wallet.address, "Message destination address mismatch"
    assert l1_to_l2_message.message_data["l2CallValue"] == eth_to_deposit, "Message value mismatch"

    retryable_ticket_result = await l1_to_l2_message.wait_for_status()
    assert retryable_ticket_result["status"] == L1ToL2MessageStatus.REDEEMED, "Retryable ticket not redeemed"

    retryable_tx_receipt = l2_signer.provider.eth.get_transaction_receipt(l1_to_l2_message.retryable_creation_id)
    assert retryable_tx_receipt is not None, "Retryable transaction receipt not found"

    l2_retryable_tx_receipt = L2TransactionReceipt(retryable_tx_receipt)
    ticket_redeem_events = l2_retryable_tx_receipt.get_redeem_scheduled_events(l2_signer.provider)

    assert len(ticket_redeem_events) == 1, "Failed finding the redeem event"
    assert ticket_redeem_events[0]["retryTxHash"] is not None, "Retry transaction hash not found"

    test_wallet_l2_eth_balance = l2_signer.provider.eth.get_balance(dest_wallet.address)
    assert test_wallet_l2_eth_balance == eth_to_deposit, "Final balance mismatch"


@pytest.mark.asyncio
async def test_withdraw_ether_transaction_succeeds():
    setup_state = await test_setup()
    l2_signer = setup_state.l2_signer
    l1_signer = setup_state.l1_signer
    eth_bridger = setup_state.eth_bridger

    fund_l2(l2_signer)
    fund_l1(l1_signer)

    eth_to_withdraw = Web3.to_wei(0.00000002, "ether")
    random_address = Account.create().address

    request = await eth_bridger.get_withdrawal_request(
        {
            "amount": eth_to_withdraw,
            "destinationAddress": random_address,
            "from": l2_signer.account.address,
            "l2Signer": l2_signer,
        }
    )

    l1_gas_estimate = request["estimateL1GasLimit"](l1_signer.provider)

    withdraw_eth_rec = await eth_bridger.withdraw(
        {
            "amount": eth_to_withdraw,
            "l2Signer": l2_signer,
            "destinationAddress": random_address,
            "from": l2_signer.account.address,
        }
    )

    assert withdraw_eth_rec.status == 1, "Initiate ETH withdraw transaction failed"

    withdraw_message = (await withdraw_eth_rec.get_l2_to_l1_messages(l1_signer))[0]

    assert withdraw_message is not None, "ETH withdraw getWithdrawalsInL2Transaction query came back empty"

    withdraw_events = await L2ToL1Message.get_l2_to_l1_events(
        l2_signer.provider, {"fromBlock": withdraw_eth_rec.block_number, "toBlock": "latest"}, None, random_address
    )
    assert len(withdraw_events) == 1, "ETH withdraw getL2ToL1EventData failed"

    message_status = await withdraw_message.status(l2_signer.provider)
    assert message_status == L2ToL1MessageStatus.UNCONFIRMED, f"ETH withdraw status returned {message_status}"

    miner1_seed = Account.create()
    miner2_seed = Account.create()

    miner1_private_key = miner1_seed.key.hex()
    miner2_private_key = miner2_seed.key.hex()

    miner1_account = Account.from_key(miner1_private_key)
    miner2_account = Account.from_key(miner2_private_key)

    miner1 = SignerOrProvider(miner1_account, l1_signer.provider)
    miner2 = SignerOrProvider(miner2_account, l2_signer.provider)

    fund_l1(miner1, Web3.to_wei(1, "ether"))
    fund_l2(miner2, Web3.to_wei(1, "ether"))
    state = {"mining": True}

    tasks = [
        mine_until_stop(miner1, state),
        mine_until_stop(miner2, state),
        withdraw_message.wait_until_ready_to_execute(l2_signer.provider),
    ]

    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    state["mining"] = False

    assert (
        await withdraw_message.status(l2_signer.provider) == L2ToL1MessageStatus.CONFIRMED
    ), "Message status should be confirmed"

    exec_rec = await withdraw_message.execute(l2_signer.provider)

    assert exec_rec.gasUsed < l1_gas_estimate, "Gas used greater than estimate"

    assert (
        await withdraw_message.status(l2_signer.provider) == L2ToL1MessageStatus.EXECUTED
    ), "Message status should be executed"

    final_random_balance = l1_signer.provider.eth.get_balance(random_address)
    assert final_random_balance == eth_to_withdraw, "L1 final balance mismatch"
