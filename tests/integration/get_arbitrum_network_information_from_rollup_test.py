import os

from dotenv import load_dotenv
from web3 import Web3, constants
from web3.providers.rpc import HTTPProvider

from arbitrum_py.data_entities.networks import (
    get_arbitrum_network,
    get_arbitrum_network_information_from_rollup,
)

load_dotenv()


class TestGetArbitrumNetworkInformationFromRollup:
    """Tests for getting Arbitrum network information from rollup"""

    def test_fetches_arbitrum_one_information(self):
        """Test fetching information about Arbitrum One"""
        arb1 = get_arbitrum_network(42161)
        eth_provider = Web3(HTTPProvider(os.environ.get("MAINNET_RPC")))

        network_info = get_arbitrum_network_information_from_rollup(arb1.eth_bridge.rollup, eth_provider)

        parent_chain_id = network_info["parentChainId"]
        confirm_period_blocks = network_info["confirmPeriodBlocks"]
        eth_bridge = network_info["ethBridge"]
        native_token = network_info["nativeToken"]

        assert parent_chain_id == arb1.parent_chain_id, "parentChainId is not correct"
        assert confirm_period_blocks == arb1.confirm_period_blocks, "confirmPeriodBlocks is not correct"

        # Check ETH bridge contracts
        bridge = eth_bridge["bridge"]
        inbox = eth_bridge["inbox"]
        sequencer_inbox = eth_bridge["sequencerInbox"]
        outbox = eth_bridge["outbox"]
        rollup = eth_bridge["rollup"]

        arb1_eth_bridge = arb1.eth_bridge

        assert bridge == arb1_eth_bridge.bridge, "Bridge contract is not correct"
        assert inbox == arb1_eth_bridge.inbox, "Inbox contract is not correct"
        assert sequencer_inbox == arb1_eth_bridge.sequencer_inbox, "SequencerInbox contract is not correct"
        assert outbox == arb1_eth_bridge.outbox, "Outbox contract is not correct"
        assert rollup == arb1_eth_bridge.rollup, "Rollup contract is not correct"

        assert native_token == constants.ADDRESS_ZERO, "Native token is not correct"

    def test_fetches_xai_information(self):
        """Test fetching information about Xai"""
        network_info = get_arbitrum_network_information_from_rollup(
            "0xC47DacFbAa80Bd9D8112F4e8069482c2A3221336",
            Web3(HTTPProvider("https://arb1.arbitrum.io/rpc")),
        )

        parent_chain_id = network_info["parentChainId"]
        confirm_period_blocks = network_info["confirmPeriodBlocks"]
        eth_bridge = network_info["ethBridge"]
        native_token = network_info["nativeToken"]

        assert parent_chain_id == 42161, "parentChainId is not correct"
        assert confirm_period_blocks == 45818, "confirmPeriodBlocks is not correct"

        # Check ETH bridge contracts
        bridge = eth_bridge["bridge"]
        inbox = eth_bridge["inbox"]
        sequencer_inbox = eth_bridge["sequencerInbox"]
        outbox = eth_bridge["outbox"]
        rollup = eth_bridge["rollup"]

        assert bridge == "0x7dd8A76bdAeBE3BBBaCD7Aa87f1D4FDa1E60f94f", "Bridge contract is not correct"
        assert inbox == "0xaE21fDA3de92dE2FDAF606233b2863782Ba046F9", "Inbox contract is not correct"
        assert sequencer_inbox == "0x995a9d3ca121D48d21087eDE20bc8acb2398c8B1", "SequencerInbox contract is not correct"
        assert outbox == "0x1E400568AD4840dbE50FB32f306B842e9ddeF726", "Outbox contract is not correct"
        assert rollup == "0xC47DacFbAa80Bd9D8112F4e8069482c2A3221336", "Rollup contract is not correct"

        assert native_token == "0x4Cb9a7AE498CEDcBb5EAe9f25736aE7d428C9D66", "Native token is not correct"
