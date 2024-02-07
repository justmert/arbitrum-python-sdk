import json

import pytest
from web3 import Web3
from web3.exceptions import TransactionNotFound

from src.lib.data_entities.networks import get_l2_network
from src.lib.inbox.inbox import InboxTools
from src.lib.utils.helper import get_contract_address, parse_raw_tx
from src.scripts.test_setup import test_setup


@pytest.fixture(scope="module")
async def test_state():
    return await test_setup()


async def send_signed_tx(test_state, info=None):
    l1_deployer = test_state.l1_deployer
    l2_deployer = test_state.l2_deployer
    l2_network = get_l2_network(l2_deployer.provider.eth.chain_id)
    inbox = InboxTools(l1_deployer, l2_network)

    message = {
        **info,
        "value": Web3.to_wei(0, "ether"),
    }
    signed_tx = await inbox.sign_l2_tx(message, l2_deployer)

    l1_tx = await inbox.send_l2_signed_tx(signed_tx)
    return {
        "signedMsg": signed_tx,
        "l1TransactionReceipt": l1_tx,
    }


def read_greeter_contract():
    with open("tests/integration/helper/greeter.json", "r") as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get("abi"):
            raise Exception("No ABI found for contract greeter")

        abi = contract_data.get("abi", None)
        bytecode = contract_data.get("bytecode_hex", None)

    return abi, bytecode


@pytest.mark.asyncio
async def test_can_deploy_contract(test_state):
    l2_deployer = test_state.l2_deployer

    abi, bytecode = read_greeter_contract()
    GreeterContract = l2_deployer.provider.eth.contract(abi=abi, bytecode=bytecode)

    construct_txn = GreeterContract.constructor().build_transaction(
        {
            "value": 0,
        }
    )
    return_data = await send_signed_tx(test_state, construct_txn)
    l1_transaction_receipt = return_data["l1TransactionReceipt"]
    signed_msg = return_data["signedMsg"]

    assert l1_transaction_receipt["status"] == 1, "L1 transaction failed"

    l2Tx = parse_raw_tx(signed_msg.rawTransaction)
    l2_tx_hash = l2Tx["hash"]
    l2_tx_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_tx_hash)

    assert l2_tx_receipt["status"] == 1, "L2 transaction failed"

    sender_address = l2Tx["from"]
    nonce = l2Tx["nonce"]

    contract_address = get_contract_address(sender_address, nonce)

    greeter = l2_deployer.provider.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    greet_result = greeter.functions.greet().call()
    assert greet_result == "hello world", "Contract returned unexpected value"


@pytest.mark.asyncio
async def test_should_confirm_same_tx_on_l2(test_state):
    l2_deployer = test_state.l2_deployer

    info = {
        "data": "0x12",
        "to": l2_deployer.account.address,
    }

    return_data = await send_signed_tx(test_state, info)
    l1_transaction_receipt = return_data["l1TransactionReceipt"]
    signed_msg = return_data["signedMsg"]

    assert l1_transaction_receipt["status"] == 1, "L1 transaction failed"

    l2Tx = parse_raw_tx(signed_msg.rawTransaction)
    l2_tx_hash = l2Tx["hash"]
    l2_tx_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_tx_hash)

    assert l2_tx_receipt["status"] == 1, "L2 transaction failed"


@pytest.mark.asyncio
async def test_send_two_tx_share_same_nonce(test_state):
    l2_deployer = test_state.l2_deployer
    current_nonce = l2_deployer.provider.eth.get_transaction_count(l2_deployer.account.address)

    low_fee_info = {
        "data": "0x12",
        "nonce": current_nonce,
        "to": l2_deployer.account.address,
        "maxFeePerGas": 10000000,
        "maxPriorityFeePerGas": 10000000,
    }

    low_fee_tx_data = await send_signed_tx(test_state, low_fee_info)
    assert low_fee_tx_data["l1TransactionReceipt"]["status"] == 1, "L1 transaction (low fee) failed"

    enough_fee_info = {
        "data": "0x12",
        "to": l2_deployer.account.address,
        "nonce": current_nonce,
    }

    enough_fee_tx_data = await send_signed_tx(test_state, enough_fee_info)
    assert enough_fee_tx_data["l1TransactionReceipt"]["status"] == 1, "L1 transaction (enough fee) failed"

    l2_low_fee_tx_hash = parse_raw_tx(low_fee_tx_data["signedMsg"].rawTransaction)["hash"]
    l2_enough_fee_tx_hash = parse_raw_tx(enough_fee_tx_data["signedMsg"].rawTransaction)["hash"]

    l2_enough_fee_receipt = l2_deployer.provider.eth.wait_for_transaction_receipt(l2_enough_fee_tx_hash)
    assert l2_enough_fee_receipt["status"] == 1, "L2 transaction (enough fee) failed"

    with pytest.raises(TransactionNotFound):
        l2_deployer.provider.eth.get_transaction_receipt(l2_low_fee_tx_hash)
