import pytest
from web3 import Web3
from eth_account import Account
from web3.exceptions import TransactionNotFound
import time
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.utils.helper import sign_and_sent_raw_transaction
from .test_helpers import fund_l1, fund_l2, mine_until_stop, wait
from src.scripts.test_setup import test_setup
from web3.exceptions import ContractLogicError
# Import or define utility functions like fund_l1, fund_l2, etc.

# Constants
AMOUNT_TO_SEND = Web3.to_wei(0.000005, 'ether')


@pytest.mark.asyncio
async def test_find_l1_batch_info():
    # Setup the environment
    setup_state = await test_setup()
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    l1_provider = l1_signer.provider
    l2_provider = l2_signer.provider

    # Set up miners (using random accounts for mining)
    miner1_seed = Account.create()
    miner2_seed = Account.create()
    
    # miner1_address = Web3.to_checksum_address(miner1_seed.address)
    # miner2_address = Web3.to_checksum_address(miner2_seed.address)
    
    miner1_private_key = miner1_seed.key.hex()  
    miner2_private_key = miner2_seed.key.hex()  

    miner1_account = Account.from_key(miner1_private_key)
    miner2_account = Account.from_key(miner2_private_key)
    
    miner1 = SignerOrProvider(miner1_account, l1_provider)
    miner2 = SignerOrProvider(miner2_account, l2_provider)

    # Fund miners
    fund_l1(miner1, Web3.to_wei(0.1, 'ether'))
    fund_l2(miner2, Web3.to_wei(0.1, 'ether'))

    # Start mining (assuming mine_until_stop is an async function to mine blocks)
    state = {'mining': True}
    mine_until_stop(miner1, state)
    mine_until_stop(miner2, state)
    print('----------------------')

    # Fund L2 signer
    fund_l2(l2_signer)

    # Send an L2 transaction and get the receipt
    random_address = Account.create().address
    rec = sign_and_sent_raw_transaction(l2_signer, {
        'to': random_address,
        'value': AMOUNT_TO_SEND
    })
    print("sent rec!")

    # tx = await l2_signer.send_transaction({
    #     'to': random_address,
    #     'value': AMOUNT_TO_SEND
    # })
    # rec = await l2_provider.eth.wait_for_transaction_receipt(tx.hash)

    # Wait for the batch data
    while True:
        wait(300)  # Sleep for 300 seconds
        try:
            # Fetch batch number and confirmations (assuming L2TransactionReceipt is a class handling this)
            arb_tx_receipt = L2TransactionReceipt(rec)
            l1_batch_number = await arb_tx_receipt.get_batch_number(l2_provider)
            l1_batch_confirmations = arb_tx_receipt.get_batch_confirmations(l2_provider)

            if l1_batch_number and l1_batch_number > 0:
                assert l1_batch_confirmations > 0, "Missing confirmations"
            
            if l1_batch_confirmations > 0:
                assert l1_batch_number > 0, "Missing batch number"

            if l1_batch_confirmations > 8:
                print('done')
                break
            
        except ContractLogicError:
            # Handle case where batch data isn't yet available
            print('not available yet')  
            pass

    # Stop mining
    state['mining'] = False


