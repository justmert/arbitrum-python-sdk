import threading
from typing import Dict

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.signer_or_provider import (
    SignerOrProvider,
)
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from tests.integration.test_helpers import (
    fund_child_signer,
    fund_parent_signer,
    mine_until_stop,
    wait,
)

AMOUNT_TO_SEND = Web3.to_wei(0.000005, "ether")


def wait_for_l1_batch_confirmations(arb_tx_receipt: ChildTransactionReceipt, l2_provider: Web3, timeout_ms: int) -> int:
    """
    Wait for L1 batch confirmations with timeout
    """
    polls = 0
    l1_batch_confirmations = 0
    MAX_POLLS = 10

    while polls < MAX_POLLS:
        l1_batch_confirmations = arb_tx_receipt.get_batch_confirmations(l2_provider)

        # Exit loop after getting non-zero confirmations
        if l1_batch_confirmations != 0:
            break

        # Increment polls and wait
        polls += 1
        wait(timeout_ms // MAX_POLLS)

    return l1_batch_confirmations


def test_find_l1_batch_info():
    """Test finding L1 batch info for child chain transaction"""
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    l2_provider = child_signer.provider

    # Set up miners
    miner1_seed = Account.create()
    miner2_seed = Account.create()

    miner1_private_key = miner1_seed.key.hex()
    miner2_private_key = miner2_seed.key.hex()

    miner1_account = Account.from_key(miner1_private_key)
    miner2_account = Account.from_key(miner2_private_key)

    miner1 = SignerOrProvider(miner1_account, parent_signer.provider)
    miner2 = SignerOrProvider(miner2_account, child_signer.provider)

    fund_parent_signer(miner1, Web3.to_wei(0.1, "ether"))
    fund_child_signer(miner2, Web3.to_wei(0.1, "ether"))

    state: Dict[str, bool] = {"mining": True}

    miner1_thread = threading.Thread(target=mine_until_stop, args=(miner1, state))
    miner2_thread = threading.Thread(target=mine_until_stop, args=(miner2, state))

    miner1_thread.start()
    miner2_thread.start()

    fund_child_signer(child_signer)

    random_address = Account.create().address

    tx = {
        "from": child_signer.account.address,
        "to": random_address,
        "value": AMOUNT_TO_SEND,
        "nonce": child_signer.provider.eth.get_transaction_count(child_signer.account.address),
        "gasPrice": child_signer.provider.eth.gas_price,
        "chainId": child_signer.provider.eth.chain_id,
    }

    estimated_gas = child_signer.provider.eth.estimate_gas(tx)
    tx["gas"] = estimated_gas

    signed_tx = child_signer.account.sign_transaction(tx)
    tx_hash = child_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    rec = child_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    # Wait for batch data
    while True:
        wait(300)
        arb_tx_receipt = ChildTransactionReceipt(rec)

        try:
            l1_batch_number = arb_tx_receipt.get_batch_number(l2_provider)
        except ContractLogicError:
            # findBatchContainingBlock errors if block number does not exist
            l1_batch_number = 0

        if l1_batch_number and l1_batch_number > 0:
            l1_batch_confirmations = wait_for_l1_batch_confirmations(
                arb_tx_receipt,
                l2_provider,
                timeout_ms=60_000,  # For L3s, also wait for batch to land on L1
            )

            assert l1_batch_confirmations > 0, "Missing confirmations"

            if l1_batch_confirmations > 8:
                break

    state["mining"] = False

    # Wait for mining threads to finish
    miner1_thread.join()
    miner2_thread.join()
