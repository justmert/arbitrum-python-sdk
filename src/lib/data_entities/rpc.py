from typing import List, TypedDict
from eth_typing import HexStr
from web3.types import BlockData as Web3Block, TxData

#
# Additional Arbitrum Block Fields
#

class ArbBlockProps(TypedDict):
    """
    Additional fields for an Arbitrum block beyond the standard Ethereum block fields.
    """
    sendRoot: HexStr
    """
    The merkle root of the withdrawals tree.
    """

    sendCount: int
    """
    Cumulative number of withdrawals since the chain's genesis.
    """

    l1BlockNumber: int
    """
    The L1 block number as perceived by this L2 block (Arbitrum concept of 'block.number' on L2).
    """


class ArbBlock(ArbBlockProps, Web3Block):
    """
    A combined data structure merging standard Web3 block data (Web3Block) 
    with Arbitrum-specific fields (ArbBlockProps).
    """
    pass


class ArbBlockWithTransactions(ArbBlock):
    """
    A block structure that also includes the list of transactions 
    (similar to `BlockWithTransactions` in ethers).

    Inherits from ArbBlock, so it has the additional Arbitrum fields as well.
    """
    transactions: List[TxData]


#
# Arbitrum-Specific Transaction Receipt
#

class ArbTransactionReceipt:
    """
    Represents an Ethereum transaction receipt 
    with additional Arbitrum-specific fields: l1BlockNumber, gasUsedForL1.
    """

    def __init__(
        self,
        l1BlockNumber: int,
        gasUsedForL1: int,
        **kwargs
    ):
        """
        :param l1BlockNumber: The L1 block number that the L2 transaction used 
                              for 'block.number' calls on Arbitrum.
        :param gasUsedForL1: The amount of gas spent on L1 computation, 
                             denominated in L2 gas units.
        :param kwargs: Any other standard or optional receipt fields 
                       (like transactionHash, status, logs, etc.).
        """
        self.l1BlockNumber = l1BlockNumber
        self.gasUsedForL1 = gasUsedForL1

        # Store any additional fields from the original receipt object
        for key, value in kwargs.items():
            setattr(self, key, value)
