import json
import pytest
from unittest.mock import MagicMock, Mock, create_autospec
from web3 import Web3, HTTPProvider
from src.lib.data_entities.networks import get_l2_network
from src.lib.message.l2_to_l1_message import L2ToL1Message
# Assuming src.lib.dataEntities.networks.get_l2_network and src.L2ToL1Message are properly defined in Python


# Set up the topics and addresses
classic_topic = '0x5baaa87db386365b5c161be377bc3d8e317e8d98d71a3ca7ed7d555340c8f767'
nitro_topic = '0x3e7aafa77dbf186b7fd488006beff893744caa3c4f6f299e8a709fa2087374fc'
arb_sys = '0x0000000000000000000000000000000000000064'

def create_provider_mock(network_choice_override=None):
    l2_network = get_l2_network(network_choice_override or 42161)

    # Create a Mock for the Web3 instance
    l2_provider_mock = Mock(spec=Web3)
    
    # Explicitly create a Mock for the eth attribute
    eth_mock = MagicMock()
    l2_provider_mock.eth = eth_mock

    latest_block = l2_network.nitro_genesis_block + 1000
    
    # Set return values and side effects on the eth mock
    eth_mock.getBlockNumber.return_value = latest_block
    eth_mock.get_block_number.return_value = latest_block
    eth_mock.get_logs.return_value = []

    l2_provider_mock.net = Mock()
    l2_provider_mock.eth.chainId = l2_network.chain_id
    l2_provider_mock.eth.chain_id = l2_network.chain_id
    l2_provider_mock.net.version = l2_network.chain_id

    return {
        'l2_provider_mock': l2_provider_mock,
        'l2_provider': l2_provider_mock,
        'l2_network': l2_network,
        'latest_block': latest_block
    }

@pytest.mark.asyncio
async def test_does_call_for_classic_events():
    provider_info = create_provider_mock()
    l2_provider = provider_info['l2_provider']
    from_block = 0
    to_block = 1000

    await L2ToL1Message.get_l2_to_l1_events(l2_provider, filter={"fromBlock": from_block, "toBlock": to_block})
    l2_provider.eth.get_logs.assert_called_once()

    l2_provider.eth.get_logs.assert_called_once_with({
        'address': arb_sys,
        'topics': [classic_topic],
        'fromBlock': 0,
        'toBlock': 1000,
    })

# You would continue defining the rest of your tests in a similar manner.
