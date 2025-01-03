from dataclasses import dataclass
from typing import Optional, Dict, List, Union, Any
from eth_typing import HexAddress
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from src.lib.data_entities.constants import (
    ARB1_NITRO_GENESIS_L2_BLOCK,
    SEVEN_DAYS_IN_SECONDS,
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import load_contract
from src.lib.utils.types import Prettify  # If you have a custom 'Prettify' type or function


@dataclass
class EthBridge:
    """
    Represents the core bridging contracts (ethBridge) on an Arbitrum chain.
    Usually includes the main 'bridge', 'inbox', 'outbox', 'rollup', etc.
    """
    bridge: HexAddress
    inbox: HexAddress
    sequencerInbox: HexAddress
    outbox: HexAddress
    rollup: HexAddress
    classicOutboxes: Optional[Dict[str, int]] = None


@dataclass
class TokenBridge:
    """
    Represents the token bridging contracts. 
    For bridging ERC20 tokens, custom tokens, WETH, etc.
    """
    parentGatewayRouter: HexAddress
    childGatewayRouter: HexAddress
    parentErc20Gateway: HexAddress
    childErc20Gateway: HexAddress
    parentCustomGateway: HexAddress
    childCustomGateway: HexAddress
    parentWethGateway: HexAddress
    childWethGateway: HexAddress
    parentWeth: HexAddress
    childWeth: HexAddress
    parentProxyAdmin: Optional[HexAddress] = None
    childProxyAdmin: Optional[HexAddress] = None
    parentMultiCall: HexAddress = ADDRESS_ZERO
    childMultiCall: HexAddress = ADDRESS_ZERO


@dataclass
class Teleporter:
    """
    Represents teleporter contracts for bridging cross-chain messages, 
    includes e.g. l2ForwarderFactory addresses, etc.
    """
    l1Teleporter: HexAddress
    l2ForwarderFactory: HexAddress


@dataclass
class ArbitrumNetwork:
    """
    Represents an Arbitrum chain, either an L2 or further child chain.
    Contains addresses for bridging, the chain ID, whether it's testnet or custom, etc.
    """
    name: str
    chainId: int
    parentChainId: int
    ethBridge: EthBridge
    tokenBridge: Optional[TokenBridge]
    teleporter: Optional[Teleporter]
    confirmPeriodBlocks: int
    isCustom: bool
    isTestnet: bool
    explorerUrl: Optional[str] = None
    retryableLifetimeSeconds: Optional[int] = None
    nativeToken: Optional[HexAddress] = None
    isBold: Optional[bool] = None


# A global dictionary storing all recognized networks by chain ID
networks: Dict[int, ArbitrumNetwork] = {}

# Pre-populate some known mainnet bridging addresses
mainnet_token_bridge = TokenBridge(
    parentGatewayRouter="0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef",
    childGatewayRouter="0x5288c571Fd7aD117beA99bF60FE0846C4E84F933",
    parentErc20Gateway="0xa3A7B6F88361F48403514059F1F16C8E78d60EeC",
    childErc20Gateway="0x09e9222E96E7B4AE2a407B98d48e330053351EEe",
    parentCustomGateway="0xcEe284F754E854890e311e3280b767F80797180d",
    childCustomGateway="0x096760F208390250649E3e8763348E783AEF5562",
    parentWethGateway="0xd92023E9d9911199a6711321D1277285e6d4e2db",
    childWethGateway="0x6c411aD3E74De3E7Bd422b94A27770f5B86C623B",
    parentWeth="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    childWeth="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    parentProxyAdmin="0x9aD46fac0Cf7f790E5be05A0F15223935A0c0aDa",
    childProxyAdmin="0xd570aCE65C43af47101fC6250FD6fC63D1c22a86",
    parentMultiCall="0x5ba1e12693dc8f9c48aad8770482f4739beed696",
    childMultiCall="0x842eC2c7D803033Edf55E478F461FC547Bc54EB2",
)

mainnet_eth_bridge = EthBridge(
    bridge="0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a",
    inbox="0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f",
    sequencerInbox="0x1c479675ad559DC151F6Ec7ed3FbF8ceE79582B6",
    outbox="0x0B9857ae2D4A3DBe74ffE1d7DF045bb7F96E4840",
    rollup="0x5eF0D09d1E6204141B4d37530808eD19f60FBa35",
    classicOutboxes={
        "0x667e23ABd27E623c11d4CC00ca3EC4d0bD63337a": 0,
        "0x760723CD2e632826c38Fef8CD438A4CC7E7E1A40": 30,
    },
)

# Register known networks
networks[42161] = ArbitrumNetwork(
    name="Arbitrum One",
    chainId=42161,
    parentChainId=1,
    ethBridge=mainnet_eth_bridge,
    tokenBridge=mainnet_token_bridge,
    teleporter=Teleporter(
        l1Teleporter="0xCBd9c6e310D6AaDeF9F025f716284162F0158992",
        l2ForwarderFactory="0x791d2AbC6c3A459E13B9AdF54Fb5e97B7Af38f87",
    ),
    confirmPeriodBlocks=45818,
    isCustom=False,
    isTestnet=False,
    explorerUrl="https://arbiscan.io",
    retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
    nativeToken=None,
)

# Additional networks, e.g. Arbitrum Nova, testnets, etc.
# networks[42170], networks[421614], etc. defined similarly...


def get_arbitrum_networks() -> List[ArbitrumNetwork]:
    """
    Returns all Arbitrum networks registered in the SDK, including default
    and any custom registrations.
    """
    return list(networks.values())


def is_parent_network(parent_chain_or_chain_id: Union[ArbitrumNetwork, int]) -> bool:
    """
    Determines if a given chain (or chain ID) is a parent of any other chain.

    :param parent_chain_or_chain_id: Either an ArbitrumNetwork object or chain ID (int).
    :return: True if at least one chain references `parent_chain_id` as its parent, else False.
    """
    parent_chain_id = (
        parent_chain_or_chain_id.chainId
        if isinstance(parent_chain_or_chain_id, ArbitrumNetwork)
        else parent_chain_or_chain_id
    )
    return any(net.parentChainId == parent_chain_id for net in get_arbitrum_networks())


def get_children_for_network(
    parent_chain_or_chain_id: Union[ArbitrumNetwork, int]
) -> List[ArbitrumNetwork]:
    """
    Returns all child chains that have the specified chain as their parent.

    :param parent_chain_or_chain_id: Either an ArbitrumNetwork or a chain ID (int).
    :return: A list of ArbitrumNetwork objects that are children of the given chain.
    """
    parent_chain_id = (
        parent_chain_or_chain_id.chainId
        if isinstance(parent_chain_or_chain_id, ArbitrumNetwork)
        else parent_chain_or_chain_id
    )
    return [c for c in get_arbitrum_networks() if c.parentChainId == parent_chain_id]


async def get_arbitrum_network(
    provider_or_chain_id: Union[SignerOrProvider, int]
) -> ArbitrumNetwork:
    """
    Returns the ArbitrumNetwork associated with the given provider or chain ID.

    If an int is provided, tries to find a matching chain ID in the pre-registered networks.
    If a provider is provided, fetches the chain ID from the provider and matches that.

    :param provider_or_chain_id: A chain ID (int) or a provider-like (SignerOrProvider).
    :return: An ArbitrumNetwork matching the chain.
    """
    if isinstance(provider_or_chain_id, int):
        return get_arbitrum_network_by_chain_id(provider_or_chain_id)
    else:
        return await get_arbitrum_network_by_provider(provider_or_chain_id)


def get_arbitrum_network_by_chain_id(chain_id: int) -> ArbitrumNetwork:
    """
    Returns an ArbitrumNetwork by its chainId, or raises an error if not recognized.

    :param chain_id: The chain ID to lookup.
    :return: The matching ArbitrumNetwork.
    :raises ArbSdkError: If no network is found for the chainId.
    """
    net = next((n for n in get_arbitrum_networks() if n.chainId == chain_id), None)
    if not net:
        raise ArbSdkError(f"Unrecognized network {chain_id}.")
    return net


async def get_arbitrum_network_by_provider(provider: SignerOrProvider) -> ArbitrumNetwork:
    """
    Derives the chain ID from the provider, then looks up the corresponding ArbitrumNetwork.

    :param provider: A SignerOrProvider with a connected chain.
    :return: The matching ArbitrumNetwork.
    """
    chain_id = provider.eth.chain_id
    return get_arbitrum_network_by_chain_id(chain_id)


async def get_native_token(bridge: str, provider: SignerOrProvider) -> str:
    """
    Attempts to retrieve the 'nativeToken' address from the given bridge contract.
    If the contract doesn't define 'nativeToken()', returns AddressZero.

    :param bridge: The address of the Bridge contract.
    :param provider: A provider or signer for calling the contract.
    :return: The native token address or zero address on failure.
    """
    try:
        bridge_contract = load_contract(
            provider=provider,
            contract_name="IERC20Bridge",
            address=bridge,
            is_classic=True,
        )
        return await bridge_contract.functions.nativeToken().call()
    except Exception:
        return ADDRESS_ZERO


async def get_arbitrum_network_information_from_rollup(
    rollup_address: str, parent_provider: SignerOrProvider
) -> Dict[str, Any]:
    """
    Retrieves Arbitrum network data from a rollup contract on the parent chain.

    :param rollup_address: The address of the Rollup contract on parent chain.
    :param parent_provider: A signer/provider for that parent chain.
    :return: A dictionary with keys:
             {
               "parentChainId",
               "confirmPeriodBlocks",
               "ethBridge": {...},
               "nativeToken": ...
             }
    """
    rollup = load_contract(
        provider=parent_provider,
        contract_name="RollupAdminLogic",
        address=rollup_address,
        is_classic=True,
    )
    chain_id = parent_provider.eth.chain_id
    bridge = await rollup.functions.bridge().call()
    inbox = await rollup.functions.inbox().call()
    sequencer_inbox = await rollup.functions.sequencerInbox().call()
    outbox = await rollup.functions.outbox().call()
    confirm_period_blocks = await rollup.functions.confirmPeriodBlocks().call()

    return {
        "parentChainId": chain_id,
        "confirmPeriodBlocks": confirm_period_blocks,
        "ethBridge": {
            "bridge": bridge,
            "inbox": inbox,
            "sequencerInbox": sequencer_inbox,
            "outbox": outbox,
            "rollup": rollup_address,
        },
        "nativeToken": await get_native_token(bridge, parent_provider),
    }


def register_custom_arbitrum_network(
    network: ArbitrumNetwork,
    options: Optional[Dict[str, bool]] = None
) -> ArbitrumNetwork:
    """
    Registers a custom (user-defined) Arbitrum network in the global 'networks' dictionary.

    :param network: The ArbitrumNetwork to register. Must have 'isCustom=True'.
    :param options: Optionally pass 'throwIfAlreadyRegistered=True' to raise an error
                    if this chainId is already present.
    :return: The same ArbitrumNetwork that was registered.
    :raises ArbSdkError: If 'isCustom' is not True or if chain already exists & throwIfAlreadyRegistered = True.
    """
    throw_if_already_registered = options.get("throwIfAlreadyRegistered", False) if options else False

    if not network.isCustom:
        raise ArbSdkError(
            f"Custom network {network.chainId} must have isCustom flag set to true"
        )

    if network.chainId in networks:
        message = f"Network {network.chainId} already included"
        if throw_if_already_registered:
            raise ArbSdkError(message)
        print(f"Warning: {message}")

    networks[network.chainId] = network
    return network


def create_network_state_handler():
    """
    Creates a handler to reset networks to an initial default state. 
    Useful for development or testing when you want to revert the 'networks' dict.
    """
    initial_state = networks.copy()

    def reset_networks_to_default():
        networks.clear()
        networks.update(initial_state)

    return {"resetNetworksToDefault": reset_networks_to_default}


def get_nitro_genesis_block(
    arbitrum_chain_or_chain_id: Union[ArbitrumNetwork, int]
) -> int:
    """
    Returns the block number where Nitro upgrade began for a given chain.
    For Arbitrum One, returns ARB1_NITRO_GENESIS_L2_BLOCK; otherwise 0.

    :param arbitrum_chain_or_chain_id: ArbitrumNetwork or chain ID int
    :return: Nitro genesis block number (e.g. 22207817 for Arbitrum One)
    """
    chain_id = (
        arbitrum_chain_or_chain_id.chainId
        if isinstance(arbitrum_chain_or_chain_id, ArbitrumNetwork)
        else arbitrum_chain_or_chain_id
    )

    # Only Arbitrum One had a distinct pre-Nitro period; 
    # all others started on Nitro from block 0.
    return ARB1_NITRO_GENESIS_L2_BLOCK if chain_id == 42161 else 0


async def get_multicall_address(
    provider_or_chain_id: Union[SignerOrProvider, int]
) -> str:
    """
    Returns the multicall contract address for a chain or for the chain 
    indicated by the given provider.
    
    If not found, attempts to see if any chain references this chain as parent 
    and returns the parent's multicall address.

    :param provider_or_chain_id: Either an int chain ID or a SignerOrProvider
    :return: The multicall address (string).
    :raises ValueError if chain not recognized
    """
    chain_id = (
        provider_or_chain_id
        if isinstance(provider_or_chain_id, int)
        else provider_or_chain_id.eth.chain_id
    )

    # If the chain is recognized in 'networks'
    chain = next((c for c in get_arbitrum_networks() if c.chainId == chain_id), None)
    if chain:
        assert_arbitrum_network_has_token_bridge(chain)
        return chain.tokenBridge.childMultiCall  # Return the child chain's multicall

    # If not recognized, see if any chain references this chain as its parent
    child_chain = next((c for c in get_arbitrum_networks() if c.parentChainId == chain_id), None)
    if not child_chain:
        raise ValueError(f"Failed to retrieve Multicall address for chain: {chain_id}")

    assert_arbitrum_network_has_token_bridge(child_chain)
    return child_chain.tokenBridge.parentMultiCall


def map_l2_network_token_bridge_to_token_bridge(input_bridge) -> TokenBridge:
    """
    Maps the older L2Network.tokenBridge object (SDK v3) to the new v4 TokenBridge format.

    :param input_bridge: The legacy object with fields like l1GatewayRouter, l2GatewayRouter, etc.
    :return: A new TokenBridge dataclass instance reflecting the updated naming conventions.
    """
    return TokenBridge(
        parentGatewayRouter=input_bridge.l1GatewayRouter,
        childGatewayRouter=input_bridge.l2GatewayRouter,
        parentErc20Gateway=input_bridge.l1ERC20Gateway,
        childErc20Gateway=input_bridge.l2ERC20Gateway,
        parentCustomGateway=input_bridge.l1CustomGateway,
        childCustomGateway=input_bridge.l2CustomGateway,
        parentWethGateway=input_bridge.l1WethGateway,
        childWethGateway=input_bridge.l2WethGateway,
        parentWeth=input_bridge.l1Weth,
        childWeth=input_bridge.l2Weth,
        parentProxyAdmin=input_bridge.l1ProxyAdmin,
        childProxyAdmin=input_bridge.l2ProxyAdmin,
        parentMultiCall=input_bridge.l1MultiCall,
        childMultiCall=input_bridge.l2Multicall,
    )


def map_l2_network_to_arbitrum_network(l2_network) -> ArbitrumNetwork:
    """
    Maps the old L2Network object (SDK v3) to a new ArbitrumNetwork (SDK v4).
    Retains other fields while renaming chainID -> chainId, partnerChainID -> parentChainId, etc.

    :param l2_network: The old L2Network object
    :return: A new ArbitrumNetwork object 
    """
    return ArbitrumNetwork(
        **{
            **l2_network.__dict__,
            "chainId": l2_network.chainID,
            "parentChainId": l2_network.partnerChainID,
            "tokenBridge": map_l2_network_token_bridge_to_token_bridge(l2_network.tokenBridge),
        }
    )


def assert_arbitrum_network_has_token_bridge(network: ArbitrumNetwork) -> None:
    """
    Asserts that the given ArbitrumNetwork has a valid TokenBridge object. 
    Used for network calls that require bridging info.

    :param network: The ArbitrumNetwork
    :raises ArbSdkError: If 'network.tokenBridge' is None or missing
    """
    if not network or not network.tokenBridge:
        raise ArbSdkError(
            f"The ArbitrumNetwork object with chainId {network.chainId} is missing "
            "the token bridge contracts addresses. Please provide them in 'tokenBridge'."
        )


def is_arbitrum_network_native_token_ether(network: ArbitrumNetwork) -> bool:
    """
    Checks if a network uses ETH as its native/gas token. 
    If 'nativeToken' is unset or AddressZero, it's ETH-based.

    :param network: The ArbitrumNetwork 
    :return: True if ETH-based, False if a custom ERC20 is used as the gas token.
    """
    return (network.nativeToken is None) or (network.nativeToken == ADDRESS_ZERO)


# Create and expose our state handler
network_handler = create_network_state_handler()
reset_networks_to_default = network_handler["resetNetworksToDefault"]
