from src.lib import inbox
from .test_helpers import (
    fund_l1,
    fund_l2,
    withdraw_token,
    mine_until_stop,
    skip_if_mainnet
)
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.data_entities.message import L2ToL1MessageStatus
from src.scripts.test_setup import test_setup
import pytest
from eth_account import Account
from web3 import Web3


# @pytest.mark.asyncio
# async def test_transfers_ether_on_l2():
#     # Setup test environment
#     setup_state = await test_setup()
#     l2_signer = setup_state.l2_signer

#     # Fund L2 signer
#     fund_l2(l2_signer)

#     # Create a random address
#     random_address = Account.create().address
#     amount_to_send = Web3.to_wei(0.000005, 'ether')

#     # Check balance before transaction
#     balance_before = l2_signer.provider.eth.get_balance(l2_signer.account.address)

#     tx = {

#         'to': random_address,
#         'value': amount_to_send,
#         # 'gas': 21000,  # Standard gas limit for Ether transfer
#         'maxFeePerGas': 15000000000,
#         'maxPriorityFeePerGas': 0,
#         # 'gasPrice': l2_signer.provider.eth.gas_price,
#         'nonce': l2_signer.provider.eth.get_transaction_count(l2_signer.account.address),
#         'chainId': l2_signer.provider.eth.chain_id
#     }
    
#     # estimate gas  
#     gas_estimate = l2_signer.provider.eth.estimate_gas(tx)
#     tx['gas'] = gas_estimate

#     # Send transaction
#     tx = l2_signer.account.sign_transaction(tx)

#     # Send the transaction to the network
#     tx_hash = l2_signer.provider.eth.send_raw_transaction(tx.rawTransaction)
#     tx_receipt = l2_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

#     # Check balances after transaction
#     balance_after = l2_signer.provider.eth.get_balance(l2_signer.account.address)
#     random_balance_after = l2_signer.provider.eth.get_balance(random_address)

#     # Assertions
#     assert Web3.from_wei(random_balance_after, 'ether') == Web3.from_wei(amount_to_send, 'ether'), "Random address balance after should match the sent amount"
#     expected_balance_after = balance_before - tx_receipt.gasUsed * tx_receipt.effectiveGasPrice - amount_to_send
#     assert balance_after == expected_balance_after, "L2 signer balance after should be correctly reduced"


@pytest.mark.asyncio
async def test_deposits_ether():
    # Setup test environment
    setup_state = await test_setup()
    eth_bridger = setup_state.eth_bridger
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    initial_test_wallet_l2_eth_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)

    # Fund L1 signer
    fund_l1(l1_signer)

    # Retrieve initial balance of the inbox contract
    inbox_address = eth_bridger.l2_network.eth_bridge.inbox
    initial_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)
    print('initial_inbox_balance', initial_inbox_balance)

    # Perform Ether deposit
    eth_to_deposit = Web3.to_wei(0.0002, 'ether')
    rec = await eth_bridger.deposit({
        'amount': eth_to_deposit,
        'l1Signer': l1_signer,
    })

    print("rec", rec)
    # deposit_receipt =  l1_signer.provider.eth.wait_for_transaction_receipt(rec.hash)

    # Verify transaction success
    assert rec.status == 1, "ETH deposit L1 transaction failed"

    # Check final balance of the inbox contract
    final_inbox_balance = l1_signer.provider.eth.get_balance(inbox_address)

    # Also fails in TS implementation - https://github.com/OffchainLabs/arbitrum-sdk/pull/407
    # assert final_inbox_balance == initial_inbox_balance + eth_to_deposit, "Balance failed to update after ETH deposit"  
    wait_result = await rec.wait_for_l2(l2_signer.provider)

    # Retrieve L1 to L2 message and verify
    l1_to_l2_messages = await rec.get_eth_deposits(l2_signer.provider)
    
    assert len(l1_to_l2_messages) == 1, "Failed to find 1 L1 to L2 message"
    l1_to_l2_message = l1_to_l2_messages[0]

    wallet_address = l1_signer.account.address
    print("l1_to_l2_message",l1_to_l2_message)
    assert l1_to_l2_message.to_address == wallet_address, "Message inputs value error"
    print('l1_to_l2_message.value', l1_to_l2_message.value)
    print('eth_to_deposit', eth_to_deposit)
    assert l1_to_l2_message.value == eth_to_deposit, "Message inputs value error"
    
    print(wait_result['message'])
    print('l2TxHash: ', wait_result['message'].l2_deposit_tx_receipt)
    print('l2 transaction found!')
    print(wait_result['complete'])
    print(wait_result)
    assert wait_result['complete'], "Eth deposit not complete"
    assert wait_result['l2_tx_receipt'] is not None

    # Check final L2 balance
    final_test_wallet_l2_eth_balance = l2_signer.provider.eth.get_balance(l2_signer.account.address)
    assert final_test_wallet_l2_eth_balance == initial_test_wallet_l2_eth_balance +  eth_to_deposit, "Final balance incorrect"

