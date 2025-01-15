import json

import pytest
from web3 import Web3
from web3.exceptions import TransactionNotFound

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.inbox.inbox import InboxTools
from arbitrum_py.utils.helper import get_contract_address, parse_raw_tx


@pytest.fixture(scope="module")
def test_state():
    return setup_testing_env()


def send_signed_tx(test_state, info=None):
    parent_deployer = test_state.parent_deployer
    child_deployer = test_state.child_deployer
    child_chain = get_arbitrum_network(child_deployer.provider.eth.chain_id)
    inbox = InboxTools(parent_deployer, child_chain)

    message = {
        **info,
        "value": Web3.to_wei(0, "ether"),
    }
    signed_tx = inbox.sign_child_tx(message, child_deployer)

    parent_tx = inbox.send_child_signed_tx(signed_tx)
    return {
        "signedMsg": signed_tx,
        "parentTransactionReceipt": parent_tx,
    }


def read_greeter_contract():
    with open("tests/integration/helper/greeter.json", "r") as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get("abi"):
            raise Exception("No ABI found for contract greeter")

        abi = contract_data.get("abi", None)
        bytecode = contract_data.get("bytecode_hex", None)

    return abi, bytecode


def test_can_deploy_contract(test_state):
    child_deployer = test_state.child_deployer

    abi, bytecode = read_greeter_contract()
    GreeterContract = child_deployer.provider.eth.contract(abi=abi, bytecode=bytecode)

    construct_txn = GreeterContract.constructor().build_transaction(
        {
            "value": 0,
        }
    )

    return_data = send_signed_tx(test_state, construct_txn)
    parent_transaction_receipt = return_data["parentTransactionReceipt"]
    signed_msg = return_data["signedMsg"]

    assert parent_transaction_receipt["status"] == 1, "Parent transaction failed"

    child_tx = parse_raw_tx(signed_msg)
    child_tx_hash = child_tx["hash"]
    child_tx_receipt = child_deployer.provider.eth.wait_for_transaction_receipt(child_tx_hash)

    assert child_tx_receipt["status"] == 1, "Child transaction failed"

    sender_address = child_tx["from"]
    nonce = child_tx["nonce"]

    contract_address = get_contract_address(sender_address, nonce)

    greeter = child_deployer.provider.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    greet_result = greeter.functions.greet().call()
    assert greet_result == "hello world", "Contract returned unexpected value"


def test_should_confirm_same_tx_on_child_chain(test_state):
    child_deployer = test_state.child_deployer

    info = {
        "data": "0x12",
        "to": child_deployer.account.address,
    }

    return_data = send_signed_tx(test_state, info)
    parent_transaction_receipt = return_data["parentTransactionReceipt"]
    signed_msg = return_data["signedMsg"]

    assert parent_transaction_receipt["status"] == 1, "Parent transaction failed"

    child_tx = parse_raw_tx(signed_msg)
    child_tx_hash = child_tx["hash"]
    child_tx_receipt = child_deployer.provider.eth.wait_for_transaction_receipt(child_tx_hash)

    assert child_tx_receipt["status"] == 1, "Child transaction failed"


def test_send_two_tx_share_same_nonce(test_state):
    child_deployer = test_state.child_deployer
    current_nonce = child_deployer.provider.eth.get_transaction_count(child_deployer.account.address)

    low_fee_info = {
        "data": "0x12",
        "nonce": current_nonce,
        "to": child_deployer.account.address,
        "maxFeePerGas": 10000000,  # 0.01 gwei
        "maxPriorityFeePerGas": 1000000,  # 0.001 gwei
    }

    low_fee_tx_data = send_signed_tx(test_state, low_fee_info)
    assert low_fee_tx_data["parentTransactionReceipt"]["status"] == 1, "Parent transaction (low fee) failed"

    enough_fee_info = {
        "data": "0x12",
        "to": child_deployer.account.address,
        "nonce": current_nonce,
    }

    enough_fee_tx_data = send_signed_tx(test_state, enough_fee_info)
    assert enough_fee_tx_data["parentTransactionReceipt"]["status"] == 1, "Parent transaction (enough fee) failed"

    child_low_fee_tx_hash = parse_raw_tx(low_fee_tx_data["signedMsg"])["hash"]
    child_enough_fee_tx_hash = parse_raw_tx(enough_fee_tx_data["signedMsg"])["hash"]

    child_enough_fee_receipt = child_deployer.provider.eth.wait_for_transaction_receipt(child_enough_fee_tx_hash)
    assert child_enough_fee_receipt["status"] == 1, "Child transaction (enough fee) failed"

    with pytest.raises(TransactionNotFound):
        child_deployer.provider.eth.get_transaction_receipt(child_low_fee_tx_hash)
