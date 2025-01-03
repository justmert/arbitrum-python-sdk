from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union

from eth_typing import HexAddress
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from src.lib.data_entities.constants import ARB1_NITRO_GENESIS_L2_BLOCK, SEVEN_DAYS_IN_SECONDS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import CaseDict, load_contract, Prettify


@dataclass
class Network:
    """Base network interface"""
    name: str
    chainId: int
    explorerUrl: str
    isCustom: bool
    gif: Optional[str] = None


@dataclass
class EthBridge:
    """Core bridge contracts"""
    bridge: HexAddress
    inbox: HexAddress
    sequencerInbox: HexAddress
    outbox: HexAddress
    rollup: HexAddress
    classicOutboxes: Optional[Dict[str, int]] = None


@dataclass
class TokenBridge:
    """Token bridge contracts"""
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
    parentMultiCall: HexAddress
    childMultiCall: HexAddress


@dataclass
class Teleporter:
    """Teleporter contracts"""
    l1Teleporter: HexAddress 
    l2ForwarderFactory: HexAddress


@dataclass
class ArbitrumNetwork(Network):
    """Represents an Arbitrum chain"""
    parentChainId: int
    ethBridge: EthBridge
    tokenBridge: Optional[TokenBridge]
    teleporter: Optional[Teleporter]
    confirmPeriodBlocks: int
    retryableLifetimeSeconds: Optional[int]
    nativeToken: Optional[HexAddress]
    isTestnet: bool
    isBold: Optional[bool] = None


networks: Dict[int, ArbitrumNetwork] = {}

mainnet_token_bridge = TokenBridge(
    parentGatewayRouter="0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef",
    childGatewayRouter="0x5288c571Fd7aD117beA99bF60FE0846C4E84F933",
    parentErc20Gateway="0xa3A7B6F88361F48403514059F1F16C8E78d60EeC",
    childErc20Gateway="0x09e9222E96E7B4AE2a407B98d48e330053351EEe",
    parentCustomGateway="0xcEe284F754E854890e311e3280b767F80797180d",
    childCustomGateway="0x096760F208390250649E3e8763348E783AEF5562",
    parentWethGateway="0xd92023E9d9911199a6711321D1277285e6d4e2db",
    childWethGateway="0x6c411aD3E74De3E7Bd422b94A27770f5B86C623B",
    childWeth="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    parentWeth="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
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

# Initialize networks dict with arbitrum chains
networks[42161] = ArbitrumNetwork(
    chainId=42161,
    name="Arbitrum One",
    explorerUrl="https://arbiscan.io", 
    isCustom=False,
    parentChainId=1,
    ethBridge=mainnet_eth_bridge,
    tokenBridge=mainnet_token_bridge,
    teleporter=Teleporter(
        l1Teleporter="0xCBd9c6e310D6AaDeF9F025f716284162F0158992",
        l2ForwarderFactory="0x791d2AbC6c3A459E13B9AdF54Fb5e97B7Af38f87",
    ),
    confirmPeriodBlocks=45818,
    retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
    nativeToken=None,
    isTestnet=False,
)
networks[42170] = ArbitrumNetwork(
    chainId=42170,
    name="Arbitrum Nova",
    explorerUrl="https://nova.arbiscan.io",
    isCustom=False,
    parentChainId=1,
    ethBridge=EthBridge(
        bridge="0xC1Ebd02f738644983b6C4B2d440b8e77DdE276Bd",
        inbox="0xc4448b71118c9071Bcb9734A0EAc55D18A153949",
        sequencerInbox="0x211E1c4c7f1bF5351Ac850Ed10FD68CFfCF6c21b",
        outbox="0xD4B80C3D7240325D18E645B49e6535A3Bf95cc58",
        rollup="0xFb209827c58283535b744575e11953DCC4bEAD88",
    ),
    tokenBridge=TokenBridge(
        parentGatewayRouter="0xC840838Bc438d73C16c2f8b22D2Ce3669963cD48",
        childGatewayRouter="0x21903d3F8176b1a0c17E953Cd896610Be9fFDFa8",
        parentErc20Gateway="0xB2535b988dcE19f9D71dfB22dB6da744aCac21bf",
        childErc20Gateway="0xcF9bAb7e53DDe48A6DC4f286CB14e05298799257",
        parentCustomGateway="0x23122da8C581AA7E0d07A36Ff1f16F799650232f",
        childCustomGateway="0xbf544970E6BD77b21C6492C281AB60d0770451F4",
        parentWethGateway="0xE4E2121b479017955Be0b175305B35f312330BaE",
        childWethGateway="0x7626841cB6113412F9c88D3ADC720C9FAC88D9eD",
        parentWeth="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        childWeth="0x722E8BdD2ce80A4422E880164f2079488e115365",
        parentProxyAdmin="0xa8f7DdEd54a726eB873E98bFF2C95ABF2d03e560",
        childProxyAdmin="0xada790b026097BfB36a5ed696859b97a96CEd92C",
        parentMultiCall="0x8896D23AfEA159a5e9b72C9Eb3DC4E2684A38EA3",
        childMultiCall="0x5e1eE626420A354BbC9a95FeA1BAd4492e3bcB86",
    ),
    teleporter=Teleporter(
        l1Teleporter="0xCBd9c6e310D6AaDeF9F025f716284162F0158992",
        l2ForwarderFactory="0x791d2AbC6c3A459E13B9AdF54Fb5e97B7Af38f87",
    ),
    confirmPeriodBlocks=45818,
    retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
    nativeToken=None,
    isTestnet=False,
)

networks[421614] = ArbitrumNetwork(
    chainId=421614,
    name="Arbitrum Rollup Sepolia Testnet",
    explorerUrl="https://sepolia.arbiscan.io",
    isCustom=False,
    parentChainId=11155111,
    ethBridge=EthBridge(
        bridge="0x38f918D0E9F1b721EDaA41302E399fa1B79333a9",
        inbox="0xaAe29B0366299461418F5324a79Afc425BE5ae21",
        sequencerInbox="0x6c97864CE4bEf387dE0b3310A44230f7E3F1be0D",
        outbox="0x65f07C7D521164a4d5DaC6eB8Fac8DA067A3B78F",
        rollup="0xd80810638dbDF9081b72C1B33c65375e807281C8",
    ),
    tokenBridge=TokenBridge(
        parentGatewayRouter="0xcE18836b233C83325Cc8848CA4487e94C6288264",
        childGatewayRouter="0x9fDD1C4E4AA24EEc1d913FABea925594a20d43C7",
        parentErc20Gateway="0x902b3E5f8F19571859F4AB1003B960a5dF693aFF",
        childErc20Gateway="0x6e244cD02BBB8a6dbd7F626f05B2ef82151Ab502",
        parentCustomGateway="0xba2F7B6eAe1F9d174199C5E4867b563E0eaC40F3",
        childCustomGateway="0x8Ca1e1AC0f260BC4dA7Dd60aCA6CA66208E642C5",
        parentWethGateway="0xA8aD8d7e13cbf556eE75CB0324c13535d8100e1E",
        childWethGateway="0xCFB1f08A4852699a979909e22c30263ca249556D",
        parentWeth="0x7b79995e5f793A07Bc00c21412e50Ecae098E7f9",
        childWeth="0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
        parentProxyAdmin="0xDBFC2FfB44A5D841aB42b0882711ed6e5A9244b0",
        childProxyAdmin="0x715D99480b77A8d9D603638e593a539E21345FdF",
        parentMultiCall="0xded9AD2E65F3c4315745dD915Dbe0A4Df61b2320",
        childMultiCall="0xA115146782b7143fAdB3065D86eACB54c169d092",
    ),
    teleporter=Teleporter(
        l1Teleporter="0x9E86BbF020594D7FFe05bF32EEDE5b973579A968",
        l2ForwarderFactory="0x88feBaFBb4E36A4E7E8874E4c9Fd73A9D59C2E7c",
    ),
    confirmPeriodBlocks=20,
    retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
    nativeToken=None,
    isTestnet=True,
)

# Add other networks here similar to the TS version...

def is_parent_network(parent_chain_or_chain_id: Union[ArbitrumNetwork, int]) -> bool:
    """Determines if a chain is a parent of any other chain"""
    parent_chain_id = parent_chain_or_chain_id.chainId if isinstance(parent_chain_or_chain_id, ArbitrumNetwork) else parent_chain_or_chain_id
    return any(c.parentChainId == parent_chain_id for c in get_arbitrum_networks())

def get_children_for_network(parent_chain_or_chain_id: Union[ArbitrumNetwork, int]) -> List[ArbitrumNetwork]:
    """Returns list of children chains for the given chain"""
    parent_chain_id = parent_chain_or_chain_id.chainId if isinstance(parent_chain_or_chain_id, ArbitrumNetwork) else parent_chain_or_chain_id
    return [chain for chain in get_arbitrum_networks() if chain.parentChainId == parent_chain_id]

async def get_arbitrum_network(provider_or_chain_id: Union[SignerOrProvider, int]) -> ArbitrumNetwork:
    """Returns the Arbitrum chain associated with the given provider or chain id"""
    if isinstance(provider_or_chain_id, int):
        return get_arbitrum_network_by_chain_id(provider_or_chain_id)
    return await get_arbitrum_network_by_provider(provider_or_chain_id)

def get_arbitrum_network_by_chain_id(chain_id: int) -> ArbitrumNetwork:
    """Get Arbitrum network by chain ID"""
    network = next((n for n in get_arbitrum_networks() if n.chainId == chain_id), None)
    if not network:
        raise ArbSdkError(f"Unrecognized network {chain_id}.")
    return network

async def get_arbitrum_network_by_provider(provider: SignerOrProvider) -> ArbitrumNetwork:
    """Get Arbitrum network from provider"""
    chain_id = provider.eth.chain_id
    return get_arbitrum_network_by_chain_id(chain_id)



async def get_native_token(bridge: str, provider: SignerOrProvider) -> str:
    """Get native token address from bridge contract"""
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

def get_arbitrum_networks() -> List[ArbitrumNetwork]:
    """Returns all registered Arbitrum networks"""
    return list(networks.values())

async def get_arbitrum_network_information_from_rollup(
    rollup_address: str, 
    parent_provider: SignerOrProvider
) -> Dict:
    """Get network information from rollup contract"""
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
    """Register a custom Arbitrum network"""
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
    """Create handler for resetting networks state"""
    initial_state = networks.copy()
    
    def reset_networks_to_default():
        networks.clear()
        networks.update(initial_state)
    
    return {"resetNetworksToDefault": reset_networks_to_default}

def get_nitro_genesis_block(arbitrum_chain_or_chain_id: Union[ArbitrumNetwork, int]) -> int:
    """Get Nitro genesis block for network"""
    chain_id = (
        arbitrum_chain_or_chain_id.chainId 
        if isinstance(arbitrum_chain_or_chain_id, ArbitrumNetwork)
        else arbitrum_chain_or_chain_id
    )
    
    # All networks except Arbitrum One started with Nitro
    return ARB1_NITRO_GENESIS_L2_BLOCK if chain_id == 42161 else 0

async def get_multicall_address(provider_or_chain_id: Union[SignerOrProvider, int]) -> str:
    """Get multicall contract address for network"""
    chains = get_arbitrum_networks()
    
    chain_id = (
        provider_or_chain_id if isinstance(provider_or_chain_id, int)
        else provider_or_chain_id.eth.chain_id
    )
    
    chain = next((c for c in chains if c.chainId == chain_id), None)
    
    if chain:
        assert_arbitrum_network_has_token_bridge(chain)
        return chain.tokenBridge.childMultiCall
    
    # Try to find chain that references this as parent
    child_chain = next((c for c in chains if c.parentChainId == chain_id), None)
    
    if not child_chain:
        raise ValueError(f"Failed to retrieve Multicall address for chain: {chain_id}")
    
    assert_arbitrum_network_has_token_bridge(child_chain)
    return child_chain.tokenBridge.parentMultiCall

def map_l2_network_token_bridge_to_token_bridge(input_bridge) -> TokenBridge:
    """Map legacy L2Network token bridge to new format"""
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
    """Map legacy L2Network to new ArbitrumNetwork format"""
    return ArbitrumNetwork(
        **{
            **l2_network.__dict__,
            "chainId": l2_network.chainID,
            "parentChainId": l2_network.partnerChainID,
            "tokenBridge": map_l2_network_token_bridge_to_token_bridge(l2_network.tokenBridge),
        }
    )

def assert_arbitrum_network_has_token_bridge(network: ArbitrumNetwork):
    """Assert network has token bridge configuration"""
    if not network or not hasattr(network, "tokenBridge") or not network.tokenBridge:
        raise ArbSdkError(
            f"The ArbitrumNetwork object with chainId {network.chainId} is missing the token bridge "
            "contracts addresses. Please add them in the 'tokenBridge' property."
        )

def is_arbitrum_network_native_token_ether(network: ArbitrumNetwork) -> bool:
    """Check if network uses ETH as native token"""
    return not network.nativeToken or network.nativeToken == ADDRESS_ZERO

# Create network state handler
network_handler = create_network_state_handler()
reset_networks_to_default = network_handler["resetNetworksToDefault"]
