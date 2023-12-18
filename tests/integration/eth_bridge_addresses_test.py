import os
import pytest
from web3 import Web3
from dotenv import load_dotenv

# Assuming the functions `get_eth_bridge_information` and `get_l2_network` are implemented in your Python code
from src.lib.data_entities.networks import get_eth_bridge_information, get_l2_network 

load_dotenv()

def test_obtain_deployed_bridge_addresses():
    arb_one_l2_network = get_l2_network(42161)
    eth_provider = Web3(Web3.HTTPProvider(os.getenv("MAINNET_RPC")))

    # Obtain on-chain information
    eth_bridge = get_eth_bridge_information(arb_one_l2_network.eth_bridge.rollup, eth_provider)

    # Assertions
    assert arb_one_l2_network.eth_bridge.bridge == eth_bridge.bridge, "Bridge contract is not correct"
    assert arb_one_l2_network.eth_bridge.inbox == eth_bridge.inbox, "Inbox contract is not correct"
    assert arb_one_l2_network.eth_bridge.sequencer_inbox == eth_bridge.sequencer_inbox, "SequencerInbox contract is not correct"
    assert arb_one_l2_network.eth_bridge.outbox == eth_bridge.outbox, "Outbox contract is not correct"
