from web3 import Web3

from src.lib.data_entities.constants import SEVEN_DAYS_IN_SECONDS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import CaseDict, load_contract


class Network(CaseDict):
    def __init__(self, chainID, name, explorerUrl, isCustom, gif=None):
        super().__init__(
            {
                "chainID": chainID,
                "name": name,
                "explorerUrl": explorerUrl,
                "isCustom": isCustom,
                "gif": gif,
            }
        )


class L1Network(Network):
    def __init__(self, partnerChainIDs, blockTime, isArbitrum, **kwargs):
        super().__init__(**kwargs)
        self.partnerChainIDs = partnerChainIDs
        self.blockTime = blockTime
        self.isArbitrum = isArbitrum


class L2Network(Network):
    def __init__(
        self,
        tokenBridge,
        ethBridge,
        partnerChainID,
        isArbitrum,
        confirmPeriodBlocks,
        retryableLifetimeSeconds,
        nitroGenesisBlock,
        nitroGenesisL1Block,
        depositTimeout,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tokenBridge = tokenBridge
        self.ethBridge = ethBridge
        self.partnerChainID = partnerChainID
        self.isArbitrum = isArbitrum
        self.confirmPeriodBlocks = confirmPeriodBlocks
        self.retryableLifetimeSeconds = retryableLifetimeSeconds
        self.nitroGenesisBlock = nitroGenesisBlock
        self.nitroGenesisL1Block = nitroGenesisL1Block
        self.depositTimeout = depositTimeout


class TokenBridge(CaseDict):
    def __init__(
        self,
        l1GatewayRouter,
        l2GatewayRouter,
        l1ERC20Gateway,
        l2ERC20Gateway,
        l1CustomGateway,
        l2CustomGateway,
        l1WethGateway,
        l2WethGateway,
        l2Weth,
        l1Weth,
        l1ProxyAdmin,
        l2ProxyAdmin,
        l1MultiCall,
        l2Multicall,
        l2MultiCall=None,
    ):
        super().__init__(
            {
                "l1GatewayRouter": l1GatewayRouter,
                "l2GatewayRouter": l2GatewayRouter,
                "l1ERC20Gateway": l1ERC20Gateway,
                "l2ERC20Gateway": l2ERC20Gateway,
                "l1CustomGateway": l1CustomGateway,
                "l2CustomGateway": l2CustomGateway,
                "l1WethGateway": l1WethGateway,
                "l2WethGateway": l2WethGateway,
                "l2Weth": l2Weth,
                "l1Weth": l1Weth,
                "l1ProxyAdmin": l1ProxyAdmin,
                "l2ProxyAdmin": l2ProxyAdmin,
                "l1MultiCall": l1MultiCall,
                "l2Multicall": l2Multicall,
                "l2MultiCall": l2MultiCall if l2MultiCall is not None else l2Multicall,
            }
        )


class EthBridge(CaseDict):
    def __init__(self, bridge, inbox, sequencerInbox, outbox, rollup, classicOutboxes=None):
        super().__init__(
            {
                "bridge": bridge,
                "inbox": inbox,
                "sequencerInbox": sequencerInbox,
                "outbox": outbox,
                "rollup": rollup,
                "classicOutboxes": classicOutboxes if classicOutboxes else {},
            }
        )


mainnet_token_bridge = TokenBridge(
    l1GatewayRouter="0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef",
    l2GatewayRouter="0x5288c571Fd7aD117beA99bF60FE0846C4E84F933",
    l1ERC20Gateway="0xa3A7B6F88361F48403514059F1F16C8E78d60EeC",
    l2ERC20Gateway="0x09e9222E96E7B4AE2a407B98d48e330053351EEe",
    l1CustomGateway="0xcEe284F754E854890e311e3280b767F80797180d",
    l2CustomGateway="0x096760F208390250649E3e8763348E783AEF5562",
    l1WethGateway="0xd92023E9d9911199a6711321D1277285e6d4e2db",
    l2WethGateway="0x6c411aD3E74De3E7Bd422b94A27770f5B86C623B",
    l2Weth="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    l1Weth="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    l1ProxyAdmin="0x9aD46fac0Cf7f790E5be05A0F15223935A0c0aDa",
    l2ProxyAdmin="0xd570aCE65C43af47101fC6250FD6fC63D1c22a86",
    l1MultiCall="0x5ba1e12693dc8f9c48aad8770482f4739beed696",
    l2Multicall="0x842eC2c7D803033Edf55E478F461FC547Bc54EB2",
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

l1_networks = {
    1: L1Network(
        chainID=1,
        name="Mainnet",
        explorerUrl="https://etherscan.io",
        partnerChainIDs=[42161, 42170],
        blockTime=14,
        isCustom=False,
        isArbitrum=False,
    ),
    1338: L1Network(
        chainID=1338,
        name="Hardhat_Mainnet_Fork",
        explorerUrl="https://etherscan.io",
        partnerChainIDs=[42161],
        blockTime=1,
        isCustom=False,
        isArbitrum=False,
    ),
    5: L1Network(
        blockTime=15,
        chainID=5,
        explorerUrl="https://goerli.etherscan.io",
        isCustom=False,
        name="Goerli",
        partnerChainIDs=[421613],
        isArbitrum=False,
    ),
    11155111: L1Network(
        chainID=11155111,
        name="Sepolia",
        explorerUrl="https://sepolia.etherscan.io",
        partnerChainIDs=[421614],
        blockTime=12,
        isCustom=False,
        isArbitrum=False,
    ),
}

l2_networks = {
    42161: L2Network(
        chainID=42161,
        name="Arbitrum One",
        explorerUrl="https://arbiscan.io",
        partnerChainID=1,
        isArbitrum=True,
        tokenBridge=mainnet_token_bridge,
        ethBridge=mainnet_eth_bridge,
        confirmPeriodBlocks=45818,
        isCustom=False,
        retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
        nitroGenesisBlock=22207817,
        nitroGenesisL1Block=15447158,
        depositTimeout=1800000,
    ),
    421613: L2Network(
        chainID=421613,
        confirmPeriodBlocks=20,
        retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
        ethBridge=EthBridge(
            bridge="0xaf4159A80B6Cc41ED517DB1c453d1Ef5C2e4dB72",
            inbox="0x6BEbC4925716945D46F0Ec336D5C2564F419682C",
            outbox="0x45Af9Ed1D03703e480CE7d328fB684bb67DA5049",
            rollup="0x45e5cAea8768F42B385A366D3551Ad1e0cbFAb17",
            sequencerInbox="0x0484A87B144745A2E5b7c359552119B6EA2917A9",
        ),
        explorerUrl="https://goerli.arbiscan.io",
        isArbitrum=True,
        isCustom=False,
        name="Arbitrum Rollup Goerli Testnet",
        partnerChainID=5,
        tokenBridge=TokenBridge(
            l1CustomGateway="0x9fDD1C4E4AA24EEc1d913FABea925594a20d43C7",
            l1ERC20Gateway="0x715D99480b77A8d9D603638e593a539E21345FdF",
            l1GatewayRouter="0x4c7708168395aEa569453Fc36862D2ffcDaC588c",
            l1MultiCall="0xa0A8537a683B49ba4bbE23883d984d4684e0acdD",
            l1ProxyAdmin="0x16101A84B00344221E2983190718bFAba30D9CeE",
            l1Weth="0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6",
            l1WethGateway="0x6e244cD02BBB8a6dbd7F626f05B2ef82151Ab502",
            l2CustomGateway="0x8b6990830cF135318f75182487A4D7698549C717",
            l2ERC20Gateway="0x2eC7Bc552CE8E51f098325D2FcF0d3b9d3d2A9a2",
            l2GatewayRouter="0xE5B9d8d42d656d1DcB8065A6c012FE3780246041",
            l2Multicall="0x108B25170319f38DbED14cA9716C54E5D1FF4623",
            l2ProxyAdmin="0xeC377B42712608B0356CC54Da81B2be1A4982bAb",
            l2Weth="0xe39Ab88f8A4777030A534146A9Ca3B52bd5D43A3",
            l2WethGateway="0xf9F2e89c8347BD96742Cc07095dee490e64301d6",
        ),
        nitroGenesisBlock=0,
        nitroGenesisL1Block=0,
        #  * Low validator participation on goerli means that it can take a long time to finalise
        #  * Wait 10 epochs there on goerli = 320 blocks. Each block is 12 seconds.
        depositTimeout=3960000,
    ),
    42170: L2Network(
        chainID=42170,
        confirmPeriodBlocks=45818,
        ethBridge=EthBridge(
            bridge="0xC1Ebd02f738644983b6C4B2d440b8e77DdE276Bd",
            inbox="0xc4448b71118c9071Bcb9734A0EAc55D18A153949",
            outbox="0xD4B80C3D7240325D18E645B49e6535A3Bf95cc58",
            rollup="0xFb209827c58283535b744575e11953DCC4bEAD88",
            sequencerInbox="0x211E1c4c7f1bF5351Ac850Ed10FD68CFfCF6c21b",
        ),
        explorerUrl="https=//nova.arbiscan.io",
        isArbitrum=True,
        isCustom=False,
        name="Arbitrum Nova",
        partnerChainID=1,
        retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
        tokenBridge=TokenBridge(
            l1CustomGateway="0x23122da8C581AA7E0d07A36Ff1f16F799650232f",
            l1ERC20Gateway="0xB2535b988dcE19f9D71dfB22dB6da744aCac21bf",
            l1GatewayRouter="0xC840838Bc438d73C16c2f8b22D2Ce3669963cD48",
            l1MultiCall="0x8896D23AfEA159a5e9b72C9Eb3DC4E2684A38EA3",
            l1ProxyAdmin="0xa8f7DdEd54a726eB873E98bFF2C95ABF2d03e560",
            l1Weth="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            l1WethGateway="0xE4E2121b479017955Be0b175305B35f312330BaE",
            l2CustomGateway="0xbf544970E6BD77b21C6492C281AB60d0770451F4",
            l2ERC20Gateway="0xcF9bAb7e53DDe48A6DC4f286CB14e05298799257",
            l2GatewayRouter="0x21903d3F8176b1a0c17E953Cd896610Be9fFDFa8",
            l2Multicall="0x5e1eE626420A354BbC9a95FeA1BAd4492e3bcB86",
            l2ProxyAdmin="0xada790b026097BfB36a5ed696859b97a96CEd92C",
            l2Weth="0x722E8BdD2ce80A4422E880164f2079488e115365",
            l2WethGateway="0x7626841cB6113412F9c88D3ADC720C9FAC88D9eD",
        ),
        nitroGenesisBlock=0,
        nitroGenesisL1Block=0,
        #  * Finalisation on mainnet can be up to 2 epochs = 64 blocks on mainnet
        #  * We add 10 minutes for the system to create and redeem the ticket, plus some extra buffer of time
        #  * (Total timeout: 30 minutes)
        depositTimeout=1800000,
    ),
    421614: L2Network(
        chainID=421614,
        confirmPeriodBlocks=20,
        ethBridge=EthBridge(
            bridge="0x38f918D0E9F1b721EDaA41302E399fa1B79333a9",
            inbox="0xaAe29B0366299461418F5324a79Afc425BE5ae21",
            outbox="0x65f07C7D521164a4d5DaC6eB8Fac8DA067A3B78F",
            rollup="0xd80810638dbDF9081b72C1B33c65375e807281C8",
            sequencerInbox="0x6c97864CE4bEf387dE0b3310A44230f7E3F1be0D",
        ),
        explorerUrl="https://sepolia-explorer.arbitrum.io",
        isArbitrum=True,
        isCustom=False,
        name="Arbitrum Rollup Sepolia Testnet",
        partnerChainID=11155111,
        retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
        tokenBridge=TokenBridge(
            l1CustomGateway="0xba2F7B6eAe1F9d174199C5E4867b563E0eaC40F3",
            l1ERC20Gateway="0x902b3E5f8F19571859F4AB1003B960a5dF693aFF",
            l1GatewayRouter="0xcE18836b233C83325Cc8848CA4487e94C6288264",
            l1MultiCall="0xded9AD2E65F3c4315745dD915Dbe0A4Df61b2320",
            l1ProxyAdmin="0xDBFC2FfB44A5D841aB42b0882711ed6e5A9244b0",
            l1Weth="0x7b79995e5f793A07Bc00c21412e50Ecae098E7f9",
            l1WethGateway="0xA8aD8d7e13cbf556eE75CB0324c13535d8100e1E",
            l2CustomGateway="0x8Ca1e1AC0f260BC4dA7Dd60aCA6CA66208E642C5",
            l2ERC20Gateway="0x6e244cD02BBB8a6dbd7F626f05B2ef82151Ab502",
            l2GatewayRouter="0x9fDD1C4E4AA24EEc1d913FABea925594a20d43C7",
            l2Multicall="0xA115146782b7143fAdB3065D86eACB54c169d092",
            l2ProxyAdmin="0x715D99480b77A8d9D603638e593a539E21345FdF",
            l2Weth="0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
            l2WethGateway="0xCFB1f08A4852699a979909e22c30263ca249556D",
        ),
        nitroGenesisBlock=0,
        nitroGenesisL1Block=0,
        depositTimeout=1800000,
    ),
    23011913: L2Network(
        chainID=23011913,
        confirmPeriodBlocks=20,
        ethBridge=EthBridge(
            bridge="0x35aa95ac4747D928E2Cd42FE4461F6D9d1826346",
            inbox="0xe1e3b1CBaCC870cb6e5F4Bdf246feB6eB5cD351B",
            outbox="0x98fcA8bFF38a987B988E54273Fa228A52b62E43b",
            rollup="0x94db9E36d9336cD6F9FfcAd399dDa6Cc05299898",
            sequencerInbox="0x00A0F15b79d1D3e5991929FaAbCF2AA65623530c",
        ),
        explorerUrl="https://stylus-testnet-explorer.arbitrum.io",
        isArbitrum=True,
        isCustom=False,
        name="Stylus Testnet",
        partnerChainID=421614,
        retryableLifetimeSeconds=SEVEN_DAYS_IN_SECONDS,
        tokenBridge=TokenBridge(
            l1CustomGateway="0xd624D491A5Bc32de52a2e1481846752213bF7415",
            l1ERC20Gateway="0x7348Fdf6F3e090C635b23D970945093455214F3B",
            l1GatewayRouter="0x0057892cb8bb5f1cE1B3C6f5adE899732249713f",
            l1MultiCall="0xBEbe3BfBF52FFEA965efdb3f14F2101c0264c940",
            l1ProxyAdmin="0xB9E77732f32831f09e2a50D6E71B2Cca227544bf",
            l1Weth="0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
            l1WethGateway="0x39845e4a230434D218b907459a305eBA61A790d4",
            l2CustomGateway="0xF6dbB0e312dF4652d59ce405F5E00CC3430f19c5",
            l2ERC20Gateway="0xe027f79CE40a1eF8e47B51d0D46Dc4ea658C5860",
            l2GatewayRouter="0x4c3a1f7011F02Fe4769fC704359c3696a6A60D89",
            l2Multicall="0xEb4A260FD16aaf18c04B1aeaDFE20E622e549bd3",
            l2ProxyAdmin="0xE914c0d417E8250d0237d2F4827ed3612e6A9C3B",
            l2Weth="0x61Dc4b961D2165623A25EB775260785fE78BD37C",
            l2WethGateway="0x7021B4Edd9f047772242fc948441d6e0b9121175",
        ),
        nitroGenesisBlock=0,
        nitroGenesisL1Block=0,
        depositTimeout=900000,
    ),
}


def get_network(signer_or_provider_or_chain_id, layer):
    if isinstance(signer_or_provider_or_chain_id, int):
        chain_id = signer_or_provider_or_chain_id

    elif isinstance(signer_or_provider_or_chain_id, Web3):
        chain_id = signer_or_provider_or_chain_id.eth.chain_id

    elif isinstance(signer_or_provider_or_chain_id, SignerOrProvider):
        chain_id = signer_or_provider_or_chain_id.provider.eth.chain_id
    else:
        raise ArbSdkError(
            f"Please provide a Web3 instance or chain ID. You have provided {type(signer_or_provider_or_chain_id)}"
        )

    networks = l1_networks if layer == 1 else l2_networks
    if chain_id in networks:
        return networks[chain_id]
    else:
        raise ArbSdkError(f"Unrecognized network {chain_id}.")


def get_l1_network(signer_or_provider_or_chain_id):
    return get_network(signer_or_provider_or_chain_id, 1)


def get_l2_network(signer_or_provider_or_chain_id):
    return get_network(signer_or_provider_or_chain_id, 2)


def get_eth_bridge_information(rollup_contract_address, l1_signer_or_provider):
    rollup = load_contract(
        provider=l1_signer_or_provider,
        contract_name="RollupAdminLogic",
        address=rollup_contract_address,
        is_classic=False,
    )
    bridge = rollup.functions.bridge().call()
    inbox = rollup.functions.inbox().call()
    sequencer_inbox = rollup.functions.sequencerInbox().call()
    outbox = rollup.functions.outbox().call()

    return EthBridge(
        bridge=bridge,
        inbox=inbox,
        sequencerInbox=sequencer_inbox,
        outbox=outbox,
        rollup=rollup_contract_address,
    )


def add_custom_network(custom_l1_network, custom_l2_network):
    if custom_l1_network:
        if int(custom_l1_network["chainID"]) in l1_networks:
            raise ArbSdkError(f"Network {custom_l1_network['chainID']} already included")
        elif not custom_l1_network["isCustom"]:
            raise ArbSdkError(f"Custom network {custom_l1_network['chainID']} must have isCustom flag set to true")
        else:
            l1_networks[custom_l1_network["chainID"]] = custom_l1_network

    if custom_l2_network["chainID"] in l2_networks:
        raise ArbSdkError(f"Network {custom_l2_network['chainID']} already included")
    elif not custom_l2_network["isCustom"]:
        raise ArbSdkError(f"Custom network {custom_l2_network['chainID']} must have isCustom flag set to true")

    l2_networks[custom_l2_network["chainID"]] = custom_l2_network

    l1_partner_chain = l1_networks.get(custom_l2_network["partnerChainID"])
    if not l1_partner_chain:
        raise ArbSdkError(
            f"Network {custom_l2_network['chainID']}'s partner network, {custom_l2_network['partnerChainID']}, not recognized"
        )

    if custom_l2_network["chainID"] not in l1_partner_chain["partnerChainIDs"]:
        l1_partner_chain["partnerChainIDs"].append(custom_l2_network["chainID"])


def add_default_local_network():
    default_local_l1_network = L1Network(
        chainID=1337,
        name="EthLocal",
        explorerUrl="",
        partnerChainIDs=[412346],
        blockTime=10,
        isCustom=True,
        isArbitrum=False,
    )
    default_local_l2_network = L2Network(
        chainID=412346,
        name="ArbLocal",
        explorerUrl="",
        partnerChainID=1337,
        confirmPeriodBlocks=20,
        ethBridge=EthBridge(
            bridge="0x2b360A9881F21c3d7aa0Ea6cA0De2a3341d4eF3C",
            inbox="0xfF4a24b22F94979E9ba5f3eb35838AA814bAD6F1",
            outbox="0x49940929c7cA9b50Ff57a01d3a92817A414E6B9B",
            rollup="0x65a59D67Da8e710Ef9A01eCa37f83f84AEdeC416",
            sequencerInbox="0xE7362D0787b51d8C72D504803E5B1d6DcdA89540",
        ),
        tokenBridge=TokenBridge(
            l1CustomGateway="0x3DF948c956e14175f43670407d5796b95Bb219D8",
            l1ERC20Gateway="0x4A2bA922052bA54e29c5417bC979Daaf7D5Fe4f4",
            l1GatewayRouter="0x525c2aBA45F66987217323E8a05EA400C65D06DC",
            l1MultiCall="0xDB2D15a3EB70C347E0D2C2c7861cAFb946baAb48",
            l1ProxyAdmin="0xe1080224B632A93951A7CFA33EeEa9Fd81558b5e",
            l1Weth="0x408Da76E87511429485C32E4Ad647DD14823Fdc4",
            l1WethGateway="0xF5FfD11A55AFD39377411Ab9856474D2a7Cb697e",
            l2CustomGateway="0x525c2aBA45F66987217323E8a05EA400C65D06DC",
            l2ERC20Gateway="0xe1080224B632A93951A7CFA33EeEa9Fd81558b5e",
            l2GatewayRouter="0x1294b86822ff4976BfE136cB06CF43eC7FCF2574",
            l2Multicall="0xDB2D15a3EB70C347E0D2C2c7861cAFb946baAb48",
            l2ProxyAdmin="0xda52b25ddB0e3B9CC393b0690Ac62245Ac772527",
            l2Weth="0x408Da76E87511429485C32E4Ad647DD14823Fdc4",
            l2WethGateway="0x4A2bA922052bA54e29c5417bC979Daaf7D5Fe4f4",
        ),
        retryableLifetimeSeconds=604800,
        nitroGenesisBlock=0,
        nitroGenesisL1Block=0,
        depositTimeout=900000,
        isCustom=True,
        isArbitrum=True,
    )

    add_custom_network(default_local_l1_network, default_local_l2_network)
    return {
        "l1_network": default_local_l1_network,
        "l2_network": default_local_l2_network,
    }


def is_l1_network(network):
    return hasattr(network, "partner_chain_ids")
