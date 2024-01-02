import pytest
from unittest.mock import Mock, create_autospec
from web3 import Web3
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.data_entities.networks import get_l2_network, l1_network, l2_network
from unittest.mock import Mock, patch
import pytest
from src.lib.data_entities.signer_or_provider import SignerProviderUtils  # Replace with actual imports
from src.lib.data_entities.errors import MissingProviderArbSdkError  # Replace with the actual import
from web3 import Web3, eth
from unittest.mock import patch, MagicMock
from web3 import Web3, EthereumTesterProvider
import asyncio 

classic_topic = '0x5baaa87db386365b5c161be377bc3d8e317e8d98d71a3ca7ed7d555340c8f767'
nitro_topic = '0x3e7aafa77dbf186b7fd488006beff893744caa3c4f6f299e8a709fa2087374fc'
arb_sys = '0x0000000000000000000000000000000000000064'
# Helper function to return async results
def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f

# Mock provider creation function
def create_provider_mock(network_choice_override=None):
    # l2_network = get_l2_network(network_choice_override or 42161)
    # print(l2_network.chain_id)
    latest_block = l2_network.nitro_genesis_block + 1000

    # Mock the Web3 provider
    provider = EthereumTesterProvider()
    web3 = Web3(provider)

    # Mock the actual network calls
    with patch.object(web3.eth, 'get_block_number', return_value=async_return(latest_block)), \
         patch.object(web3.eth, 'get_logs', return_value=async_return([])):
        #  patch.object(web3.eth, 'get_network', return_value=async_return(l2_network.chain_id)):
        return web3, l2_network, latest_block

# Test case for classic events
@pytest.mark.asyncio
async def test_does_call_for_classic_events():
    web3, l2_network, _ = create_provider_mock()
    from_block = 0
    to_block = 1000

    # Call your function with the mocked provider
    # Make sure this function uses the `get_logs` method of the Web3 object.
    await L2ToL1Message.get_l2_to_l1_events(web3, filter={"fromBlock": from_block, "toBlock": to_block})

    # Now you can assert that get_logs was called correctly
    # But remember, you're asserting on the mock of the EthereumTesterProvider, not the Web3 object directly.
    web3.eth.get_logs.assert_called_once_with({
        'address': arb_sys,
        'topics': [classic_topic],
        'fromBlock': from_block,
        'toBlock': to_block
    })


# Repeat the above pattern for the other test cases (nitro events, classic and nitro events, etc.)

# @pytest.mark.asyncio
# async def test_does_call_for_nitro_events():
#     l2_provider_mock, l2_network, _ = create_provider_mock()
#     from_block = l2_network.nitro_genesis_block
#     to_block = l2_network.nitro_genesis_block + 500

#     await L2ToL1Message.get_l2_to_l1_events(l2_provider_mock, filter= {"fromBlock": from_block, "toBlock": to_block})

#     l2_provider_mock.getLogs.assert_called_once_with({
#         'address': arb_sys,
#         'topics': [nitro_topic],
#         'fromBlock': from_block,
#         'toBlock': to_block
#     })

# @pytest.mark.asyncio
# async def test_does_call_for_classic_and_nitro_events():
#     l2_provider_mock, l2_network, _ = create_provider_mock()
#     from_block = 0
#     to_block = l2_network.nitro_genesis_block + 500

#     await L2ToL1Message.get_l2_to_l1_events(l2_provider_mock, filter= {"fromBlock": from_block, "toBlock": to_block})

#     l2_provider_mock.getLogs.assert_any_call({
#         'address': arb_sys,
#         'topics': [classic_topic],
#         'fromBlock': 0,
#         'toBlock': l2_network.nitro_genesis_block
#     })
#     l2_provider_mock.getLogs.assert_any_call({
#         'address': arb_sys,
#         'topics': [nitro_topic],
#         'fromBlock': l2_network.nitro_genesis_block,
#         'toBlock': to_block
#     })

# @pytest.mark.asyncio
# async def test_does_call_for_classic_and_nitro_events_earliest_to_latest():
#     l2_provider_mock, l2_network, _ = create_provider_mock()
#     from_block = 'earliest'
#     to_block = 'latest'

#     await L2ToL1Message.get_l2_to_l1_events(l2_provider_mock, filter= {"fromBlock": from_block, "toBlock": to_block})

#     l2_provider_mock.getLogs.assert_any_call({
#         'address': arb_sys,
#         'topics': [classic_topic],
#         'fromBlock': 0,
#         'toBlock': l2_network.nitro_genesis_block
#     })
#     l2_provider_mock.getLogs.assert_any_call({
#         'address': arb_sys,
#         'topics': [nitro_topic],
#         'fromBlock': l2_network.nitro_genesis_block,
#         'toBlock': to_block
#     })

# @pytest.mark.asyncio
# async def test_does_call_for_only_nitro_for_latest():
#     l2_provider_mock, l2_network, _ = create_provider_mock()
#     from_block = l2_network.nitro_genesis_block + 2
#     to_block = 'latest'

#     await L2ToL1Message.get_l2_to_l1_events(l2_provider_mock, filter= {"fromBlock": from_block, "toBlock": to_block})

#     l2_provider_mock.getLogs.assert_called_once_with({
#         'address': arb_sys,
#         'topics': [nitro_topic],
#         'fromBlock': from_block,
#         'toBlock': 'latest'
#     })

# @pytest.mark.asyncio
# async def test_doesnt_call_classic_when_nitro_genesis_is_0():
#     l2_provider_mock, _, _ = create_provider_mock(421613)
#     from_block = 'earliest'
#     to_block = 'latest'

#     await L2ToL1Message.get_l2_to_l1_events(l2_provider_mock, filter= {"fromBlock": from_block, "toBlock": to_block})

#     l2_provider_mock.getLogs.assert_called_once_with({
#         'address': arb_sys,
#         'topics': [nitro_topic],
#         'fromBlock': 0,
#         'toBlock': to_block
#     })
