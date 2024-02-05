from eth_typing import ChainId
import pytest
from web3 import Web3, HTTPProvider
from web3.contract import Contract
from eth_account import Account
from eth_utils import to_hex
import os
import random
import pytest
from src.lib.utils.helper import get_contract_address, load_contract, parse_raw_tx
from src.scripts.test_setup import test_setup
from src.lib.inbox.inbox import InboxTools
from src.lib.data_entities.networks import get_l2_network
from src.lib.asset_briger.erc20_bridger import AdminErc20Bridger
import json
from web3.exceptions import TransactionNotFound

from test import hex_to_bytes


@pytest.fixture(scope="module")
async def test_state():
    return await test_setup()


async def send_signed_tx(test_state, info=None):
    l1_deployer = test_state["l1_deployer"]
    l2_deployer = test_state["l2_deployer"]
    l2_network = get_l2_network(l2_deployer.provider.eth.chain_id)
    inbox = InboxTools(l1_deployer, l2_network)

    message = {
        **info,
        "value": Web3.to_wei(0, "ether"),
    }
    print("message", message)
    signed_tx = await inbox.sign_l2_tx(message, l2_deployer)

    l1_tx = await inbox.send_l2_signed_tx(signed_tx, l2_deployer)
    return {
        "signed_msg": signed_tx,
        "l1_transaction_receipt": l1_tx,
    }


# @pytest.mark.asyncio
# async def test_can_deploy_contract(test_state):
#     l2_deployer = test_state['l2_deployer']

#     with open("tests/integration/helper/greeter.json", "r") as abi_file:
#         contract_data = json.load(abi_file)
#         if not contract_data.get("abi"):
#             raise Exception(f"No ABI found for contract greeter")

#         abi = contract_data.get("abi", None)
#         bytecode = contract_data.get("bytecode_hex", None)

#     GreeterContract = l2_deployer.provider.eth.contract(abi=abi, bytecode=bytecode)

#     # chain_id = l2_deployer.provider.eth.chain_id
#     # gas_estimate = GreeterContract.constructor().estimate_gas(
#     #     {"from": l2_deployer.account.address}
#     # )

#     # Transaction for contract deployment
#     construct_txn = GreeterContract.constructor().build_transaction({
#         # 'from': l2_deployer.account.address,
#         # 'nonce': l2_deployer.provider.eth.get_transaction_count(l2_deployer.account.address),
#         'value': 0,  # No ETH to send along
#         # 'gas': gas_estimate,  # Assuming gas. Adjust as necessary.
#         # 'gasPrice': l2_deployer.provider.eth.gas_price,
#         # 'chainId': chain_id,
#     })
#     print('construct_txn', construct_txn)


#     # Send the signed transaction and wait for the L1 transaction receipt
#     return_data = await send_signed_tx(test_state, construct_txn)
#     l1_transaction_receipt = return_data['l1_transaction_receipt']
#     signed_msg = return_data['signed_msg']
#     print('signed_msg', signed_msg)
#     assert l1_transaction_receipt['status'] == 1, "L1 transaction failed"

#     # Get the deployed contract address
#     # contract_address = l1_transaction_receipt.contractAddress

#     # Check for the L2 transaction receipt
#     # l2_tx_hash = Web3.keccak(construct_txn)

#     #     const l2Tx = ethers.utils.parseTransaction(signedMsg)
#     # const l2Txhash = l2Tx.hash!
#     # l2_tx_hash = signed_msg['hash']

#     l2Tx = parse_raw_tx(signed_msg.rawTransaction)
#     l2_tx_hash = l2Tx['hash']
#     l2_tx_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_tx_hash)
#     assert l2_tx_receipt['status'] == 1, "L2 transaction failed"


#    # Attach to the deployed contract
#     # Usage
#     sender_address = l2Tx['from']  # Replace with actual sender address
#     nonce = l2Tx['nonce']         # Replace with actual nonce
#     contract_address = get_contract_address(sender_address, nonce)

#     print('contract_addresss', contract_address)
#     print("l2tx", l2Tx)
#     greeter = l2_deployer.provider.eth.contract(
#         address=Web3.to_checksum_address(contract_address),
#         abi=abi
#     )
#     # # Interact with the contract
#     greet_result = greeter.functions.greet().call()
#     assert greet_result == "hello world", "Contract returned unexpected value"


# @pytest.mark.asyncio
# async def test_should_confirm_same_tx_on_l2(test_state):
#     l2_deployer = test_state['l2_deployer']

#     # Information for the transaction
#     info = {
#         'data': '0x12',
#         'to': l2_deployer.account.address,
#     }

#     # Send the signed transaction
#     return_data = await send_signed_tx(test_state, info)
#     l1_transaction_receipt = return_data['l1_transaction_receipt']
#     signed_msg = return_data['signed_msg']

#     # Assert L1 transaction status
#     assert l1_transaction_receipt['status'] == 1, "L1 transaction failed"

#     # Parse the L2 transaction and wait for its receipt
#     l2Tx = parse_raw_tx(signed_msg.rawTransaction)
#     l2_tx_hash = l2Tx['hash']
#     l2_tx_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_tx_hash)

#     # Assert L2 transaction status
#     assert l2_tx_receipt['status'] == 1, "L2 transaction failed"


@pytest.mark.asyncio
async def test_send_two_tx_share_same_nonce(test_state):
    l2_deployer = test_state["l2_deployer"]
    current_nonce = l2_deployer.provider.eth.get_transaction_count(l2_deployer.account.address)

    # Low fee transaction info
    low_fee_info = {
        "data": "0x12",
        "nonce": current_nonce,
        "to": l2_deployer.account.address,
        "maxFeePerGas": 10000000,  # 0.01 gwei
        "maxPriorityFeePerGas": 1000000,  # 0.001 gwei
    }

    # Send low fee transaction
    low_fee_tx_data = await send_signed_tx(test_state, low_fee_info)
    assert low_fee_tx_data["l1_transaction_receipt"]["status"] == 1, "L1 transaction (low fee) failed"

    # Enough fee transaction info
    enough_fee_info = {
        "data": "0x12",
        "to": l2_deployer.account.address,
        "nonce": current_nonce,
    }

    # Send enough fee transaction
    enough_fee_tx_data = await send_signed_tx(test_state, enough_fee_info)
    assert enough_fee_tx_data["l1_transaction_receipt"]["status"] == 1, "L1 transaction (enough fee) failed"

    # Check L2 transactions
    l2_low_fee_tx_hash = parse_raw_tx(low_fee_tx_data["signed_msg"].rawTransaction)["hash"]
    l2_enough_fee_tx_hash = parse_raw_tx(enough_fee_tx_data["signed_msg"].rawTransaction)["hash"]

    # Wait for the enough fee transaction to be confirmed on L2
    l2_enough_fee_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_enough_fee_tx_hash)
    assert l2_enough_fee_receipt["status"] == 1, "L2 transaction (enough fee) failed"

    # Check if the low fee transaction is nullified
    with pytest.raises(TransactionNotFound):
        l2_deployer.provider.eth.get_transaction_receipt(l2_low_fee_tx_hash)
