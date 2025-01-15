import pytest

from arbitrum_py.data_entities.constants import ADDRESS_ZERO
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.networks import (
    dict_to_arbitrum_network_instance,
    get_arbitrum_network,
    get_arbitrum_networks,
    get_children_for_network,
    get_multicall_address,
    is_arbitrum_network_native_token_ether,
    is_parent_network,
    register_custom_arbitrum_network,
    reset_networks_to_default,
)

ETHEREUM_MAINNET_CHAIN_ID = 1
ARBITRUM_ONE_CHAIN_ID = 42161
MOCK_L2_CHAIN_ID = 222222
MOCK_L3_CHAIN_ID = 99999999


@pytest.fixture(autouse=True)
def setup():
    """Reset networks before each test"""
    reset_networks_to_default()


class TestNetworks:
    class TestAddingNetworks:
        def test_adds_custom_l2_network(self):
            arbitrum_one = get_arbitrum_network(ARBITRUM_ONE_CHAIN_ID)

            custom_arbitrum_network = {
                **arbitrum_one.__dict__,
                "chainId": MOCK_L2_CHAIN_ID,
                "parentChainId": ETHEREUM_MAINNET_CHAIN_ID,
                "isArbitrum": True,
                "isCustom": True,
            }

            register_custom_arbitrum_network(custom_arbitrum_network)

            assert get_arbitrum_network(MOCK_L2_CHAIN_ID) is not None

            # Assert network has correct parent
            arbitrum_network = get_arbitrum_network(custom_arbitrum_network["chainId"])
            assert arbitrum_network.parent_chain_id == ETHEREUM_MAINNET_CHAIN_ID

        def test_adds_custom_l3_network(self):
            arbitrum_one = get_arbitrum_network(ARBITRUM_ONE_CHAIN_ID)

            custom_arbitrum_network = {
                **arbitrum_one.__dict__,
                "chainId": MOCK_L3_CHAIN_ID,
                "parentChainId": ARBITRUM_ONE_CHAIN_ID,
                "isArbitrum": True,
                "isCustom": True,
            }

            register_custom_arbitrum_network(custom_arbitrum_network)

            assert get_arbitrum_network(MOCK_L3_CHAIN_ID) is not None

            # Assert network has correct parent
            l3_network = get_arbitrum_network(MOCK_L3_CHAIN_ID)
            assert l3_network.parent_chain_id == ARBITRUM_ONE_CHAIN_ID

    class TestFetchingNetworks:
        def test_successfully_fetches_arbitrum_network(self):
            network = get_arbitrum_network(ARBITRUM_ONE_CHAIN_ID)
            assert network.chain_id == ARBITRUM_ONE_CHAIN_ID

        def test_fails_to_fetch_registered_l1_network(self):
            with pytest.raises(ArbSdkError) as exc_info:
                get_arbitrum_network(ETHEREUM_MAINNET_CHAIN_ID)
            assert str(exc_info.value) == f"Unrecognized network {ETHEREUM_MAINNET_CHAIN_ID}."

        def test_successfully_fetches_l3_chain(self):
            arbitrum_one = get_arbitrum_network(ARBITRUM_ONE_CHAIN_ID)

            custom_l3_network = {
                **arbitrum_one.__dict__,
                "chainId": MOCK_L3_CHAIN_ID,
                "parentChainId": ARBITRUM_ONE_CHAIN_ID,
                "isArbitrum": True,
                "isCustom": True,
            }

            register_custom_arbitrum_network(custom_l3_network)

            l3_network = get_arbitrum_network(MOCK_L3_CHAIN_ID)
            assert l3_network.chain_id == MOCK_L3_CHAIN_ID
            assert l3_network.parent_chain_id == ARBITRUM_ONE_CHAIN_ID

        def test_fails_to_fetch_unrecognized_network(self):
            chain_id = 9999
            with pytest.raises(ArbSdkError) as exc_info:
                get_arbitrum_network(chain_id)
            assert str(exc_info.value) == f"Unrecognized network {chain_id}."

    class TestReturnsCorrectNetworks:
        def test_returns_correct_arbitrum_networks(self):

            arbitrum_network_ids = [n.chain_id for n in get_arbitrum_networks()]
            expected = [42161, 42170, 421614]

            assert len(arbitrum_network_ids) == len(expected)
            assert set(arbitrum_network_ids) == set(expected)

    class TestGetChildrenForNetwork:
        def test_returns_correct_children_for_ethereum_mainnet(self):
            children = [c.chain_id for c in get_children_for_network(1)]
            assert set(children) == {42161, 42170}

        def test_returns_correct_children_for_arbitrum_one(self):
            children = [c.chain_id for c in get_children_for_network(42161)]
            assert not children

        def test_returns_correct_children_for_arbitrum_nova(self):
            children = [c.chain_id for c in get_children_for_network(42170)]
            assert not children

        def test_returns_correct_children_for_sepolia(self):
            children = [c.chain_id for c in get_children_for_network(11155111)]
            assert set(children) == {421614}

        def test_returns_correct_children_for_arbitrum_sepolia(self):
            children = [c.chain_id for c in get_children_for_network(421614)]
            assert not children

    class TestIsParentNetwork:
        def test_returns_correct_value_for_ethereum_mainnet(self):
            assert is_parent_network(1) is True

        def test_returns_correct_value_for_arbitrum_one(self):
            assert is_parent_network(42161) is False

        def test_returns_correct_value_for_arbitrum_nova(self):
            assert is_parent_network(42170) is False

        def test_returns_correct_value_for_sepolia(self):
            assert is_parent_network(11155111) is True

        def test_returns_correct_value_for_arbitrum_sepolia(self):
            assert is_parent_network(421614) is False

    class TestGetMulticallAddress:
        def test_returns_correct_value_for_ethereum_mainnet(self):
            multicall = get_multicall_address(1)
            assert multicall == "0x5ba1e12693dc8f9c48aad8770482f4739beed696"

        def test_returns_correct_value_for_arbitrum_one(self):
            multicall = get_multicall_address(42161)
            assert multicall == "0x842eC2c7D803033Edf55E478F461FC547Bc54EB2"

        def test_returns_correct_value_for_arbitrum_nova(self):
            multicall = get_multicall_address(42170)
            assert multicall == "0x5e1eE626420A354BbC9a95FeA1BAd4492e3bcB86"

        def test_returns_correct_value_for_sepolia(self):
            multicall = get_multicall_address(11155111)
            assert multicall == "0xded9AD2E65F3c4315745dD915Dbe0A4Df61b2320"

        def test_returns_correct_value_for_arbitrum_sepolia(self):
            multicall = get_multicall_address(421614)
            assert multicall == "0xA115146782b7143fAdB3065D86eACB54c169d092"


class TestIsArbitrumNetworkNativeTokenEther:
    test_network = dict_to_arbitrum_network_instance(
        {
            "name": "Test Network Undefined",
            "chain_id": 123456,
            "parent_chain_id": 1,
            "eth_bridge": {
                "bridge": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "inbox": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "sequencer_inbox": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "outbox": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "rollup": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "classic_outboxes": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            },
            "token_bridge": None,
            "confirm_period_blocks": 10000,
            "is_custom": True,
            "teleporter": None,
            "is_testnet": True,
            "explorer_url": None,
            "retryable_lifetime_seconds": 604800,
            "native_token": None,  # Undefined nativeToken
            "is_bold": False,
        }
    )

    def test_returns_true_when_native_token_is_undefined(self):
        self.test_network.nativeToken = None
        assert is_arbitrum_network_native_token_ether(self.test_network) is True

    def test_returns_true_when_native_token_is_zero_address(self):
        self.test_network.nativeToken = ADDRESS_ZERO
        assert is_arbitrum_network_native_token_ether(self.test_network) is True

    def test_returns_false_when_native_token_is_valid_address(self):
        self.test_network.nativeToken = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        assert is_arbitrum_network_native_token_ether(self.test_network) is False
