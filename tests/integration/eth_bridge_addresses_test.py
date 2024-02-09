import os

from dotenv import load_dotenv
from web3 import HTTPProvider, Web3

from src.lib.data_entities.networks import get_eth_bridge_information, get_l2_network

load_dotenv()


def test_obtain_deployed_bridge_addresses():
    arb_one_l2_network = get_l2_network(42161)
    eth_provider = Web3(HTTPProvider(os.getenv("MAINNET_RPC")))

    eth_bridge = get_eth_bridge_information(arb_one_l2_network.eth_bridge.rollup, eth_provider)

    assert arb_one_l2_network.eth_bridge.bridge == eth_bridge.bridge, "Bridge contract is not correct"
    assert arb_one_l2_network.eth_bridge.inbox == eth_bridge.inbox, "Inbox contract is not correct"
    assert (
        arb_one_l2_network.eth_bridge.sequencer_inbox == eth_bridge.sequencer_inbox
    ), "SequencerInbox contract is not correct"
    assert arb_one_l2_network.eth_bridge.outbox == eth_bridge.outbox, "Outbox contract is not correct"
