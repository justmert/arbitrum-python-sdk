from web3.types import (
    BlockData as Web3Block,
)
from typing import Union
from eth_typing import HexStr
from web3 import Web3
from typing import TypedDict
from eth_typing import HexStr, ChecksumAddress
from typing import TypedDict, Union, List
from web3.types import BlockData as Web3Block, TxData, LogReceipt


class ArbBlockProps(TypedDict):
    sendRoot: HexStr
    sendCount: int
    l1BlockNumber: int


class ArbBlock(ArbBlockProps, Web3Block):
    pass


class ArbBlockWithTransactions(ArbBlock):
    transactions: List[TxData]


class ArbTransactionReceipt:
    def __init__(self, l1BlockNumber: int, gasUsedForL1: int, **kwargs):
        self.l1BlockNumber = l1BlockNumber
        self.gasUsedForL1 = gasUsedForL1

        for key, value in kwargs.items():
            setattr(self, key, value)
