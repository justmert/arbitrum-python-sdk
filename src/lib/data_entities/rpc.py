from web3.types import (
    BlockData as Web3Block,
)
from eth_typing import HexStr
from typing import TypedDict
from typing import List
from web3.types import TxData


class ArbBlockProps(TypedDict):
    sendRoot: HexStr
    sendCount: int
    l1BlockNumber: int


class ArbBlock(ArbBlockProps, Web3Block):
    pass


class ArbBlockWithTransactions(ArbBlock):
    transactions: List[TxData]


class ArbTransactionReceipt:
    def __init__(self, l1BlockNumber, gasUsedForL1, **kwargs):
        self.l1BlockNumber = l1BlockNumber
        self.gasUsedForL1 = gasUsedForL1

        for key, value in kwargs.items():
            setattr(self, key, value)
