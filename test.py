import json
from web3 import Web3
from web3.contract import Contract

def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs", 'erc20': "ERC20"}
    components = name.split('_')
    # Convert the first component as is, then title-case the remaining components
    camel_case_name = components[0] + ''.join(special_cases.get(x, x.title()) for x in components[1:])
    return camel_case_name

class CaseDict:
    def __init__(self, x):
        for key, value in x.items():
            setattr(self, key, value)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __getattr__(self, name):
        # Try to fetch the attribute as is (for camelCase or any other case)
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass

        # Convert snake_case to camelCase and try again
        camel_case_name = snake_to_camel(name)
        try:
            return super().__getattribute__(camel_case_name)
        except AttributeError:
            pass

        # If not found, raise AttributeError
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def items(self):
        return self.__dict__.items()

    def __contains__(self, key):
        return key in self.__dict__

    def __setattr__(self, name, value):
        camel_case_name = snake_to_camel(name)
        super().__setattr__(camel_case_name, value)

    def to_dict(self):
        # Convert all attributes (except special ones) to a dictionary
        return {k: self.convert_to_serializable(v) for k, v in self.__dict__.items() if not k.startswith('_')}

    def __str__(self):
        items = [f"{key}: {value}" for key, value in self.to_dict().items()]
        return f"CaseDict({', '.join(items)})"

    def convert_to_serializable(self, value):
        # Conversion logic remains the same
        if isinstance(value, CaseDict):
            return value.to_dict()
        elif isinstance(value, list):
            return [self.convert_to_serializable(item) for item in value]
        elif isinstance(value, dict):
            return {key: self.convert_to_serializable(val) for key, val in value.items()}
        elif isinstance(value, Contract):
            return value.address
        else:
            return value


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
        l2MultiCall = None
    ):
        super().__init__({
            'l1GatewayRouter': l1GatewayRouter,
            'l2GatewayRouter': l2GatewayRouter,
            'l1ERC20Gateway': l1ERC20Gateway,
            'l2ERC20Gateway': l2ERC20Gateway,
            'l1CustomGateway': l1CustomGateway,
            'l2CustomGateway': l2CustomGateway,
            'l1WethGateway': l1WethGateway,
            'l2WethGateway': l2WethGateway,
            'l2Weth': l2Weth,
            'l1Weth': l1Weth,
            'l1ProxyAdmin': l1ProxyAdmin,
            'l2ProxyAdmin': l2ProxyAdmin,
            'l1MultiCall': l1MultiCall,
            'l2Multicall': l2Multicall,
            'l2MultiCall': l2MultiCall if l2MultiCall is not None else l2Multicall
        })



class EthBridge(CaseDict):
    def __init__(
        self, bridge, inbox, sequencerInbox, outbox, rollup, classicOutboxes=None
    ):
        super().__init__({
            'bridge': bridge,
            'inbox': inbox,
            'sequencerInbox': sequencerInbox,
            'outbox': outbox,
            'rollup': rollup,
            'classicOutboxes': classicOutboxes if classicOutboxes else {}
        })


class Network(CaseDict):
    def __init__(self, chainID, name, explorerUrl, isCustom, gif=None):
        super().__init__({
            'chainID': chainID,
            'name': name,
            'explorerUrl': explorerUrl,
            'isCustom': isCustom,
            'gif': gif
        })


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



x = L2Network(
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
        retryableLifetimeSeconds=262,
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
    )

print(x, "\n")
print(x.to_dict(), "\n")
print(json.dumps(x.to_dict(), indent=4), "\n")
print(x.tokenBridge.l1CustomGateway, "\n")
print(x.tokenBridge.to_dict(), "\n")
print(x['tokenBridge']['l1CustomGateway'], "\n")
print(x['tokenBridge'].to_dict(), "\n")
print(x['token_bridge'])
print(x['nitroGenesisBlock'])
print(x['nitro_genesis_block'])
print(x.nitroGenesisBlock)
print(x.nitro_genesis_block)
