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


# class ArbBlock(ArbBlockProps, Web3Block):
#     """
#     The Arbitrum-specific block structure, extending standard Web3 block with Arbitrum properties.
#     """

#     pass


# class ArbBlockWithTransactions(ArbBlockProps, Web3Block):
#     """
#     The Arbitrum-specific block with transactions structure, extending standard Web3 block with transactions and Arbitrum properties.
#     """

#     pass

class ArbBlock(ArbBlockProps, Web3Block):
    pass


class ArbBlockWithTransactions(ArbBlock):
    transactions: List[TxData]


class ArbTransactionReceipt:
    def __init__(self, l1BlockNumber: int, gasUsedForL1: int, **kwargs):
        """
        Eth transaction receipt with additional Arbitrum specific fields.

        :param l1BlockNumber: The L1 block number that would be used for block.number calls that occur within this transaction.
        :param gasUsedForL1: Amount of gas spent on L1 computation in units of L2 gas.
        """
        self.l1BlockNumber = l1BlockNumber
        self.gasUsedForL1 = gasUsedForL1
        
        # Set additional properties from kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
