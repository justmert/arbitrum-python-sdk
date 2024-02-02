import json
from regex import W
from web3 import Web3
from web3.contract import Contract

from src.lib.utils.helper import get_address


def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs", "erc20": "ERC20"}
    components = name.split("_")
    # Convert the first component as is, then title-case the remaining components
    camel_case_name = components[0] + "".join(
        special_cases.get(x, x.title()) for x in components[1:]
    )
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
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

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
        return {
            k: self.convert_to_serializable(v)
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

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
            return {
                key: self.convert_to_serializable(val) for key, val in value.items()
            }
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
    def __init__(
        self, bridge, inbox, sequencerInbox, outbox, rollup, classicOutboxes=None
    ):
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

# print(x, "\n")
# print(x.to_dict(), "\n")
# print(json.dumps(x.to_dict(), indent=4), "\n")
# print(x.tokenBridge.l1CustomGateway, "\n")
# print(x.tokenBridge.to_dict(), "\n")
# print(x['tokenBridge']['l1CustomGateway'], "\n")
# print(x['tokenBridge'].to_dict(), "\n")
# print(x['token_bridge'])
# print(x['nitroGenesisBlock'])
# print(x['nitro_genesis_block'])
# print(x.nitroGenesisBlock)
# print(x.nitro_genesis_block)


from web3 import Web3
from eth_utils import to_checksum_address
import rlp


def hex_to_bytes(value: str) -> bytes:
    # Remove '0x' prefix if present and convert to bytes
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


# # Define your own zero padding function
# def zero_pad(value: bytes, length: int) -> bytes:
#     return value.rjust(length, b'\0')


def zero_pad(value, length):
    # Pad the value to the required length
    return value.rjust(length, b"\x00")


def format_number(value):
    hex_str = Web3.to_hex(value)[2:].lstrip("0")

    # Ensure the hex string has an even number of characters
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str
    return bytes.fromhex(hex_str)


def concat(*args) -> bytes:
    # Concatenate all byte arguments
    return b"".join(args)


def calculate_submit_retryable_id(
    l2_chain_id,
    from_address,
    message_number,
    l1_base_fee,
    dest_address,
    l2_call_value,
    l1_value,
    max_submission_fee,
    excess_fee_refund_address,
    call_value_refund_address,
    gas_limit,
    max_fee_per_gas,
    data,
):
    chain_id = l2_chain_id
    msg_num = message_number
    from_addr = to_checksum_address(from_address)
    dest_addr = (
        "0x"
        if dest_address == "0x0000000000000000000000000000000000000000"
        else to_checksum_address(dest_address)
    )
    call_value_refund_addr = to_checksum_address(call_value_refund_address)
    excess_fee_refund_addr = to_checksum_address(excess_fee_refund_address)

    fields = [
        format_number(chain_id),
        zero_pad(format_number(msg_num), 32),
        bytes.fromhex(from_addr[2:]),
        format_number(l1_base_fee),
        format_number(l1_value),
        format_number(max_fee_per_gas),
        format_number(gas_limit),
        bytes.fromhex(dest_addr[2:]) if dest_addr != "0x" else b"",
        format_number(l2_call_value),
        bytes.fromhex(call_value_refund_addr[2:]),
        format_number(max_submission_fee),
        bytes.fromhex(excess_fee_refund_addr[2:]),
        bytes.fromhex(data[2:]),
    ]

    rlp_encoded = rlp.encode(fields)
    rlp_enc_with_type = b"\x69" + rlp_encoded

    retryable_tx_id = Web3.keccak(rlp_enc_with_type)
    return retryable_tx_id.hex()



# 412346 0x70206CECb718a6B7d2C49631dc8E4048285e6a86 27 7 0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975 10000000000000000 10006300000039536 39536 0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975 0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975 21000 300000000 0x0000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e5975000000000000000000000000000000000000000000000000002386f26fc1000000000000000000000000000000000000000000000000000000238cad4504b2700000000000000000000000000000000000000000000000000000000000009a700000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e59750000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e597500000000000000000000000000000000000000000000000000000000000052080000000000000000000000000000000000000000000000000000000011e1a3000000000000000000000000000000000000000000000000000000000000000000

x = calculate_submit_retryable_id(
    l2_chain_id=412346,
    from_address="0x70206CECb718a6B7d2C49631dc8E4048285e6a86",
    message_number=27,
    l1_base_fee=7,
    dest_address="0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975",
    l2_call_value=10000000000000000,
    l1_value=10006300000039536, # 10006300000039200
    max_submission_fee=39536, # 39200
    excess_fee_refund_address="0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975",
    call_value_refund_address="0x5f0f6cECB718A6B7D2C49631DC8e4048285e5975",
    gas_limit=21000,
    max_fee_per_gas=300000000,
    data="0x", # "0x"
)
# print("creation_id" , x)
# assert x == "0x1f449efd071985a3ff8ed20fe89aff502d2fd40794b633d43e5693a3f83400fa"


from mock import call
from web3 import Web3
from eth_utils import to_checksum_address, big_endian_to_int
from eth_abi import decode


class SubmitRetryableMessageDataParser:
    """
    Parse the event data emitted in the InboxMessageDelivered event
    for messages of type L1MessageType_submitRetryableTx
    """

    @staticmethod
    def parse(event_data):
        # Assuming event_data is a hex string
        if isinstance(event_data, bytes):
            event_data = event_data.hex()

        
        if isinstance(event_data, str):
            decoded_data = decode(
                [
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                ],
                Web3.to_bytes(hexstr=event_data),
            )
        else:
            decoded_data = decode(
                [
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                ],
                event_data,
            )

        def address_from_big_number(bn):
            # Convert BigNumber to address
            return to_checksum_address(bn.to_bytes(20, byteorder="big"))

        dest_address = address_from_big_number(decoded_data[0])
        l2_call_value = decoded_data[1]
        l1_value = decoded_data[2]
        max_submission_fee = decoded_data[3]
        excess_fee_refund_address = address_from_big_number(decoded_data[4])
        call_value_refund_address = address_from_big_number(decoded_data[5])
        gas_limit = decoded_data[6]
        max_fee_per_gas = decoded_data[7]
        call_data_length = decoded_data[8]

        if isinstance(event_data, str):
            data_offset = (
                len(event_data) - 2 * call_data_length
            )  # 2 characters per byte
            data = "0x" + event_data[data_offset:]
        else:
            # Convert call data length to the number of characters in the hex string
            data_length_chars = call_data_length
            # Slice the event data from the end based on the call data length
            data_bytes = event_data[-data_length_chars:]
            # Convert the bytes to a hex string and prepend with '0x'
            data = "0x" + data_bytes.hex()

        return {
            "destAddress": dest_address,
            "l2CallValue": l2_call_value,
            "l1Value": l1_value,
            "maxSubmissionFee": max_submission_fee,
            "excessFeeRefundAddress": excess_fee_refund_address,
            "callValueRefundAddress": call_value_refund_address,
            "gasLimit": gas_limit,
            "maxFeePerGas": max_fee_per_gas,
            "data": data,
        }

# print(Web3.to_hex())
event = [
    {
        
        "inboxMessageEvent": {
            "messageNum": 23,
            'data': b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00_\x0fl\xec\xb7\x18\xa6\xb7\xd2\xc4\x961\xdc\x8e@H(^Yu\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00#\x86\xf2o\xc1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00#\x8c\xadE\x04\xb2p\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x9ap\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00_\x0fl\xec\xb7\x18\xa6\xb7\xd2\xc4\x961\xdc\x8e@H(^Yu\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00_\x0fl\xec\xb7\x18\xa6\xb7\xd2\xc4\x961\xdc\x8e@H(^Yu\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00R\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x11\xe1\xa3\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        },
        "bridgeMessageEvent": {
            "messageIndex": 23,
            "beforeInboxAcc": b'^0.\xe7\x93 l\xc4\x17\xb7\x105\xfe\xb3\x1bn\xc5\x97\x07M\x17\xb3^o\x92"E\xa8\x8bk\x0b/',
            "inbox": "0xfF4a24b22F94979E9ba5f3eb35838AA814bAD6F1",
            "kind": 9,
            "sender": "0x70206CECb718a6B7d2C49631dc8E4048285e6a86",
            "messageDataHash": b":\xf9\xed\xea2\xd0B\xda<\xc1\x85\x7f\xbcq\x9bS>m\x06\x96\x80\xc7Us\xa2\x0foax%\x96\xfe",
            "baseFeeL1": 7,
            "timestamp": 1706215034,
        },
    }
]


event2 = [
    {
        "inboxMessageEvent": {
            "messageNum": 35,
            "data": "0x0000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e5975000000000000000000000000000000000000000000000000002386f26fc1000000000000000000000000000000000000000000000000000000238cad4504b12000000000000000000000000000000000000000000000000000000000000099200000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e59750000000000000000000000005f0f6cecb718a6b7d2c49631dc8e4048285e597500000000000000000000000000000000000000000000000000000000000052080000000000000000000000000000000000000000000000000000000011e1a3000000000000000000000000000000000000000000000000000000000000000000",
        },
        "bridgeMessageEvent": {
            "messageIndex": 35,
            "beforeInboxAcc": '0xda2804b38c3a9929225e5cf30dfbd604f0115309d224c49ee43af601cfe07d12',
            "inbox": "0xfF4a24b22F94979E9ba5f3eb35838AA814bAD6F1",
            "kind": 9,
            "sender": "0x70206CECb718a6B7d2C49631dc8E4048285e6a86",
            "messageDataHash": "0x0cba2a65ecc559bf4a23455f461476e27fff5e31d27651fe72613c071fd39de5",
            "baseFeeL1": 7,
            "timestamp": 1706216259,
        },
    }
]

# print(SubmitRetryableMessageDataParser.parse(event[0]["inboxMessageEvent"]["data"]))
# print(SubmitRetryableMessageDataParser.parse(event2[0]["inboxMessageEvent"]["data"]))



signed_tx = "0x02f9086183064aba288459682f00846553f1008306e32c8080b90805608060405234801561001057600080fd5b506040518060400160405280600b81526020017f68656c6c6f20776f726c640000000000000000000000000000000000000000008152506000908051906020019061005c9291906100a3565b5033600160006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055506101a7565b8280546100af90610146565b90600052602060002090601f0160209004810192826100d15760008555610118565b82601f106100ea57805160ff1916838001178555610118565b82800160010185558215610118579182015b828111156101175782518255916020019190600101906100fc565b5b5090506101259190610129565b5090565b5b8082111561014257600081600090555060010161012a565b5090565b6000600282049050600182168061015e57607f821691505b6020821081141561017257610171610178565b5b50919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b61064f806101b66000396000f3fe608060405234801561001057600080fd5b50600436106100415760003560e01c8063a413686214610046578063cfae321714610062578063d5f3948814610080575b600080fd5b610060600480360381019061005b9190610313565b61009e565b005b61006a610148565b60405161007791906103e2565b60405180910390f35b6100886101da565b60405161009591906103c7565b60405180910390f35b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff161461012e576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161012590610404565b60405180910390fd5b8060009080519060200190610144929190610200565b5050565b6060600080546101579061050a565b80601f01602080910402602001604051908101604052809291908181526020018280546101839061050a565b80156101d05780601f106101a5576101008083540402835291602001916101d0565b820191906000526020600020905b8154815290600101906020018083116101b357829003601f168201915b5050505050905090565b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b82805461020c9061050a565b90600052602060002090601f01602090048101928261022e5760008555610275565b82601f1061024757805160ff1916838001178555610275565b82800160010185558215610275579182015b82811115610274578251825591602001919060010190610259565b5b5090506102829190610286565b5090565b5b8082111561029f576000816000905550600101610287565b5090565b60006102b66102b184610449565b610424565b9050828152602081018484840111156102d2576102d16105d0565b5b6102dd8482856104c8565b509392505050565b600082601f8301126102fa576102f96105cb565b5b813561030a8482602086016102a3565b91505092915050565b600060208284031215610329576103286105da565b5b600082013567ffffffffffffffff811115610347576103466105d5565b5b610353848285016102e5565b91505092915050565b61036581610496565b82525050565b60006103768261047a565b6103808185610485565b93506103908185602086016104d7565b610399816105df565b840191505092915050565b60006103b1601983610485565b91506103bc826105f0565b602082019050919050565b60006020820190506103dc600083018461035c565b92915050565b600060208201905081810360008301526103fc818461036b565b905092915050565b6000602082019050818103600083015261041d816103a4565b9050919050565b600061042e61043f565b905061043a828261053c565b919050565b6000604051905090565b600067ffffffffffffffff8211156104645761046361059c565b5b61046d826105df565b9050602081019050919050565b600081519050919050565b600082825260208201905092915050565b60006104a1826104a8565b9050919050565b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b82818337600083830152505050565b60005b838110156104f55780820151818401526020810190506104da565b83811115610504576000848401525b50505050565b6000600282049050600182168061052257607f821691505b602082108114156105365761053561056d565b5b50919050565b610545826105df565b810181811067ffffffffffffffff821117156105645761056361059c565b5b80604052505050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b7f4e487b7100000000000000000000000000000000000000000000000000000000600052604160045260246000fd5b600080fd5b600080fd5b600080fd5b600080fd5b6000601f19601f8301169050919050565b7f4f6e6c79206465706c6f7965722063616e20646f20746869730000000000000060008201525056fea264697066735822122006dc1f58e4dba2ce67f456ac9e8845fad95aaab9cf5682f1e35279ffd90ff2e164736f6c63430008070033c001a00feacd6e62abd5eff3295b63d0afdf7d540d0ab86e3e60fea74853fe6bb5efb3a006baf47944f893131fdab09834a8340585acee9600e693276e9e9bcdc3f8a49c"


L2MessageType_signedTx = 4


send_data = "0x0402f9086183064aba288459682f00846553f1008306e32c8080b90805608060405234801561001057600080fd5b506040518060400160405280600b81526020017f68656c6c6f20776f726c640000000000000000000000000000000000000000008152506000908051906020019061005c9291906100a3565b5033600160006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055506101a7565b8280546100af90610146565b90600052602060002090601f0160209004810192826100d15760008555610118565b82601f106100ea57805160ff1916838001178555610118565b82800160010185558215610118579182015b828111156101175782518255916020019190600101906100fc565b5b5090506101259190610129565b5090565b5b8082111561014257600081600090555060010161012a565b5090565b6000600282049050600182168061015e57607f821691505b6020821081141561017257610171610178565b5b50919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b61064f806101b66000396000f3fe608060405234801561001057600080fd5b50600436106100415760003560e01c8063a413686214610046578063cfae321714610062578063d5f3948814610080575b600080fd5b610060600480360381019061005b9190610313565b61009e565b005b61006a610148565b60405161007791906103e2565b60405180910390f35b6100886101da565b60405161009591906103c7565b60405180910390f35b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff161461012e576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161012590610404565b60405180910390fd5b8060009080519060200190610144929190610200565b5050565b6060600080546101579061050a565b80601f01602080910402602001604051908101604052809291908181526020018280546101839061050a565b80156101d05780601f106101a5576101008083540402835291602001916101d0565b820191906000526020600020905b8154815290600101906020018083116101b357829003601f168201915b5050505050905090565b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b82805461020c9061050a565b90600052602060002090601f01602090048101928261022e5760008555610275565b82601f1061024757805160ff1916838001178555610275565b82800160010185558215610275579182015b82811115610274578251825591602001919060010190610259565b5b5090506102829190610286565b5090565b5b8082111561029f576000816000905550600101610287565b5090565b60006102b66102b184610449565b610424565b9050828152602081018484840111156102d2576102d16105d0565b5b6102dd8482856104c8565b509392505050565b600082601f8301126102fa576102f96105cb565b5b813561030a8482602086016102a3565b91505092915050565b600060208284031215610329576103286105da565b5b600082013567ffffffffffffffff811115610347576103466105d5565b5b610353848285016102e5565b91505092915050565b61036581610496565b82525050565b60006103768261047a565b6103808185610485565b93506103908185602086016104d7565b610399816105df565b840191505092915050565b60006103b1601983610485565b91506103bc826105f0565b602082019050919050565b60006020820190506103dc600083018461035c565b92915050565b600060208201905081810360008301526103fc818461036b565b905092915050565b6000602082019050818103600083015261041d816103a4565b9050919050565b600061042e61043f565b905061043a828261053c565b919050565b6000604051905090565b600067ffffffffffffffff8211156104645761046361059c565b5b61046d826105df565b9050602081019050919050565b600081519050919050565b600082825260208201905092915050565b60006104a1826104a8565b9050919050565b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b82818337600083830152505050565b60005b838110156104f55780820151818401526020810190506104da565b83811115610504576000848401525b50505050565b6000600282049050600182168061052257607f821691505b602082108114156105365761053561056d565b5b50919050565b610545826105df565b810181811067ffffffffffffffff821117156105645761056361059c565b5b80604052505050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b7f4e487b7100000000000000000000000000000000000000000000000000000000600052604160045260246000fd5b600080fd5b600080fd5b600080fd5b600080fd5b6000601f19601f8301169050919050565b7f4f6e6c79206465706c6f7965722063616e20646f20746869730000000000000060008201525056fea264697066735822122006dc1f58e4dba2ce67f456ac9e8845fad95aaab9cf5682f1e35279ffd90ff2e164736f6c63430008070033c001a00feacd6e62abd5eff3295b63d0afdf7d540d0ab86e3e60fea74853fe6bb5efb3a006baf47944f893131fdab09834a8340585acee9600e693276e9e9bcdc3f8a49c"



from eth_abi import encode
import struct
from web3 import Web3


# send_data_py = encode(['uint8', 'bytes'], [L2MessageType_signedTx, Web3.to_bytes(hexstr=signed_tx)])



# Convert hex string to bytes
signed_tx_bytes = Web3.to_bytes(hexstr=signed_tx)

# InboxMessageKind.L2MessageType_signedTx as an integer
message_type = 4

# Pack the uint8 integer
packed_message_type = struct.pack("B", message_type)  # 'B' is the format code for uint8

# Concatenate the packed uint8 with the signed transaction bytes
send_data_py = packed_message_type + signed_tx_bytes

# Convert result to hex string if needed
send_data_py = Web3.to_hex(send_data_py)



# print("send_data_py", Web3.to_hex(send_data_py))
# print("send_data", send_data)
# assert Web3.to_hex(send_data_py) == send_data


# print("send_data_py", send_data_py)
# print("send_data", send_data)
assert send_data_py == send_data

from hexbytes import HexBytes
from web3 import Web3
from web3.types import AccessList, Nonce, TxData, Wei
from eth_utils import encode_hex, to_bytes
from eth.abc import SignedTransactionAPI
from eth.vm.forks.arrow_glacier.transactions import (
    ArrowGlacierTransactionBuilder as TransactionBuilder,
)
from typing import Any, Dict, cast

def parse_raw_tx_pyevm(raw_tx: str) -> SignedTransactionAPI:
    """Convert a raw transaction to a py-evm signed transaction object.

    Inspired by:
     - https://github.com/ethereum/web3.py/issues/3109#issuecomment-1737744506
     - https://snakecharmers.ethereum.org/web3-py-patterns-decoding-signed-transactions/
    """
    return TransactionBuilder().decode(to_bytes(hexstr=raw_tx))


def parse_raw_tx(raw_tx: str) -> TxData:
    """Convert a raw transaction to a web3.py TxData dict.

    Inspired by:
     - https://ethereum.stackexchange.com/a/83855/89782
     - https://docs.ethers.org/v5/api/utils/transactions/#utils-parseTransaction
    """
    tx = parse_raw_tx_pyevm(raw_tx)

    return {
        "accessList": cast(AccessList, tx.access_list),
        "blockHash": None,
        "blockNumber": None,
        "chainId": tx.chain_id,
        "data": HexBytes(Web3.to_hex(tx.data)),
        "from": Web3.to_checksum_address(encode_hex(tx.sender)),
        "gas": tx.gas,
        "gasPrice": None if tx.type_id is not None else cast(Wei, tx.gas_price),
        "maxFeePerGas": cast(Wei, tx.max_fee_per_gas),
        "maxPriorityFeePerGas": cast(Wei, tx.max_priority_fee_per_gas),
        "hash": HexBytes(tx.hash),
        "input": None,
        "nonce": cast(Nonce, tx.nonce),
        "r": HexBytes(tx.r),
        "s": HexBytes(tx.s),
        # "to": Web3.to_checksum_address(tx.to),
        "transactionIndex": None,
        "type": tx.type_id,
        "v": None,
        "value": cast(Wei, tx.value),
    }


signed_msg = "0x02f9085d83064aba3a80840bebc2008306e32c8080b90805608060405234801561001057600080fd5b506040518060400160405280600b81526020017f68656c6c6f20776f726c640000000000000000000000000000000000000000008152506000908051906020019061005c9291906100a3565b5033600160006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055506101a7565b8280546100af90610146565b90600052602060002090601f0160209004810192826100d15760008555610118565b82601f106100ea57805160ff1916838001178555610118565b82800160010185558215610118579182015b828111156101175782518255916020019190600101906100fc565b5b5090506101259190610129565b5090565b5b8082111561014257600081600090555060010161012a565b5090565b6000600282049050600182168061015e57607f821691505b6020821081141561017257610171610178565b5b50919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b61064f806101b66000396000f3fe608060405234801561001057600080fd5b50600436106100415760003560e01c8063a413686214610046578063cfae321714610062578063d5f3948814610080575b600080fd5b610060600480360381019061005b9190610313565b61009e565b005b61006a610148565b60405161007791906103e2565b60405180910390f35b6100886101da565b60405161009591906103c7565b60405180910390f35b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff161461012e576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161012590610404565b60405180910390fd5b8060009080519060200190610144929190610200565b5050565b6060600080546101579061050a565b80601f01602080910402602001604051908101604052809291908181526020018280546101839061050a565b80156101d05780601f106101a5576101008083540402835291602001916101d0565b820191906000526020600020905b8154815290600101906020018083116101b357829003601f168201915b5050505050905090565b600160009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b82805461020c9061050a565b90600052602060002090601f01602090048101928261022e5760008555610275565b82601f1061024757805160ff1916838001178555610275565b82800160010185558215610275579182015b82811115610274578251825591602001919060010190610259565b5b5090506102829190610286565b5090565b5b8082111561029f576000816000905550600101610287565b5090565b60006102b66102b184610449565b610424565b9050828152602081018484840111156102d2576102d16105d0565b5b6102dd8482856104c8565b509392505050565b600082601f8301126102fa576102f96105cb565b5b813561030a8482602086016102a3565b91505092915050565b600060208284031215610329576103286105da565b5b600082013567ffffffffffffffff811115610347576103466105d5565b5b610353848285016102e5565b91505092915050565b61036581610496565b82525050565b60006103768261047a565b6103808185610485565b93506103908185602086016104d7565b610399816105df565b840191505092915050565b60006103b1601983610485565b91506103bc826105f0565b602082019050919050565b60006020820190506103dc600083018461035c565b92915050565b600060208201905081810360008301526103fc818461036b565b905092915050565b6000602082019050818103600083015261041d816103a4565b9050919050565b600061042e61043f565b905061043a828261053c565b919050565b6000604051905090565b600067ffffffffffffffff8211156104645761046361059c565b5b61046d826105df565b9050602081019050919050565b600081519050919050565b600082825260208201905092915050565b60006104a1826104a8565b9050919050565b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b82818337600083830152505050565b60005b838110156104f55780820151818401526020810190506104da565b83811115610504576000848401525b50505050565b6000600282049050600182168061052257607f821691505b602082108114156105365761053561056d565b5b50919050565b610545826105df565b810181811067ffffffffffffffff821117156105645761056361059c565b5b80604052505050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052602260045260246000fd5b7f4e487b7100000000000000000000000000000000000000000000000000000000600052604160045260246000fd5b600080fd5b600080fd5b600080fd5b600080fd5b6000601f19601f8301169050919050565b7f4f6e6c79206465706c6f7965722063616e20646f20746869730000000000000060008201525056fea264697066735822122006dc1f58e4dba2ce67f456ac9e8845fad95aaab9cf5682f1e35279ffd90ff2e164736f6c63430008070033c001a0315dbb4fc6cfc9a2b3f8511bb76b2ba578e5fbcccb94ea8f376201669cf7aadda002c4b3d84c459fc981f6c9f84ca3fa61d1f3e63a24e0b161495e64f6f1bd7799"
# print(parse_raw_tx(signed_msg))


event_data = Web3.to_hex(b"_\x0fl\xec\xb7\x18\xa6\xb7\xd2\xc4\x961\xdc\x8e@H(^Yu\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb5\xe6 \xf4\x80\x00")

# print(event_data)
def parse_eth_deposit_data(event_data):
    # print(Web3.to_hex(event_data))
    if isinstance(event_data, bytes):
        event_data = Web3.to_hex(event_data)
    
    address_end = 2 + 20 * 2
    to_address = get_address("0x" + event_data[2:address_end])
    value_hex = event_data[address_end:]
    if value_hex.startswith("0"):
        # remove all the leading zeros
        value_hex = value_hex.lstrip("0")

    value = "0x" + value_hex
    return {"to": to_address, "value": value}

# print(parse_eth_deposit_data(event_data))



def calculate_deposit_tx_id(
    l2_chain_id, message_number, from_address, to_address, value
):
    chain_id = l2_chain_id
    msg_num = message_number

    fields = [
        format_number(chain_id),
        zero_pad(format_number(msg_num), 32),
        bytes.fromhex(get_address(from_address)[2:]),
        bytes.fromhex(get_address(to_address)[2:]),
        format_number(value),
    ]
    for field in fields:
        # Convert to an array of integers
        int_array = [byte for byte in field]

        print(int_array)

    print(fields)
    rlp_encoded = rlp.encode(fields)
    rlp_enc_with_type = b'\x64' + rlp_encoded

    retryable_tx_id = Web3.keccak(rlp_enc_with_type)
    # retryable_tx_id2 = Web3.keccak(rlp_encoded)
    # print(retryable_tx_id2.hex())

    return retryable_tx_id.hex()


x = calculate_deposit_tx_id(
    l2_chain_id=412346,
    message_number=108,
    from_address="0xB89DCA5176245D6856f4368C3B0898424FEC0fa3",
    to_address="0xA78CCA5176245d6856F4368C3b0898424feBFE92",
    value=200000000000000
)

y = "0x12909a86f1be0ba54553cfa8a1fa3495af9a0c8d9e16e3167fcc1662200b96a3"



# x = calculate_deposit_tx_id(
#     l2_chain_id=412346,
#     message_number=96,
#     from_address="0x39099490eA49bEC3c6213b750CD52C66a737F8C7",
#     to_address="0x27F89490ea49beC3c6213B750cD52C66a737E7B6",
#     value=200000000000000
# )

# y = "0xfc0da723cfaee42799959858fc386793558f3207ab16bf54cb61b9ebc2dd44cc"


print(x)
print(y)

assert x == y



# Example address
address = "0x1234567890abcdef1234567890abcdef12345678"

# Check if the address is valid
is_valid_address = Web3.is_address(address)

