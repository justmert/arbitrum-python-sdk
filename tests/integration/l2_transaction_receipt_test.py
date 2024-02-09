import asyncio

import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import fund_l1, fund_l2, mine_until_stop

AMOUNT_TO_SEND = Web3.to_wei(0.000005, "ether")


@pytest.mark.asyncio
async def test_find_l1_batch_info():
    setup_state = await test_setup()
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    l2_provider = l2_signer.provider

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

    miner1_task = asyncio.create_task(mine_until_stop(miner1, state))
    miner2_task = asyncio.create_task(mine_until_stop(miner2, state))

    fund_l2(l2_signer)

    random_address = Account.create().address

    tx = {
        "from": l2_signer.account.address,
        "to": random_address,
        "value": AMOUNT_TO_SEND,
    }

    tx_hash = l2_signer.provider.eth.send_transaction(tx)

    rec = l2_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    while True:
        await asyncio.sleep(0.3)
        arb_tx_receipt = L2TransactionReceipt(rec)
        try:
            l1_batch_number = await arb_tx_receipt.get_batch_number(l2_provider)
        except ContractLogicError:
            l1_batch_number = 0

        l1_batch_confirmations = arb_tx_receipt.get_batch_confirmations(l2_provider)

        if l1_batch_number and l1_batch_number > 0:
            assert l1_batch_confirmations > 0, "Missing confirmations"

        if l1_batch_confirmations > 0:
            assert l1_batch_number > 0, "Missing batch number"

        if l1_batch_confirmations > 8:
            break

    state["mining"] = False
    miner1_task.cancel()
    miner2_task.cancel()
