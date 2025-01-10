from typing import List, TypedDict, Dict, Any, Optional

from eth_typing import HexStr, BlockNumber, Hash32
from web3.types import BlockData as Web3Block
from web3.types import TxData, TxReceipt, LogReceipt


class ArbBlockProps(TypedDict):
    """Additional fields for an Arbitrum block beyond standard Ethereum block fields.

    This class defines the Arbitrum-specific fields that extend a standard Ethereum
    block. These fields provide information about L2->L1 messages (withdrawals) and
    L1 block number tracking.

    Attributes:
        sendRoot (HexStr): The merkle root of the withdrawals tree
        sendCount (int): Cumulative number of withdrawals since genesis
        l1BlockNumber (int): The L1 block number as seen from within this L2 block.
            This is used for block.number calls within Arbitrum transactions.
            See: https://developer.offchainlabs.com/docs/time_in_arbitrum
    """

    sendRoot: HexStr
    sendCount: int
    l1BlockNumber: int


class ArbBlock(ArbBlockProps, Web3Block):
    """An Arbitrum block combining standard Ethereum and Arbitrum-specific fields.

    This class merges standard Web3 block data (Web3Block) with Arbitrum-specific
    fields (ArbBlockProps). It provides a complete view of an Arbitrum block
    including both L1 and L2 relevant information.

    Inherits all fields from Web3Block (standard Ethereum block fields) plus:
        - All fields from ArbBlockProps
    """

    pass


class ArbBlockWithTransactions(ArbBlock):
    """An Arbitrum block that includes full transaction objects.

    Similar to ethers.js BlockWithTransactions, this class includes the full
    transaction objects rather than just transaction hashes. Useful when you
    need detailed transaction data along with the block data.

    Attributes:
        transactions (List[TxData]): List of full transaction objects included
            in this block
    """

    transactions: List[TxData]


class ArbTransactionReceipt(TxReceipt):
    """An Ethereum transaction receipt with additional Arbitrum-specific fields.

    This class extends the standard Ethereum transaction receipt with fields that
    are specific to Arbitrum's L2 execution environment, particularly around
    L1 block number tracking and L1 computation costs.

    Attributes:
        l1BlockNumber (int): The L1 block number that would be used for
            block.number calls occurring within this transaction. See:
            https://developer.offchainlabs.com/docs/time_in_arbitrum
        gasUsedForL1 (int): Amount of gas spent on L1 computation, denominated
            in L2 gas units
        transactionHash (Hash32): Hash of the transaction
        transactionIndex (int): Integer of the transaction's index position in the block
        blockHash (Hash32): Hash of the block where this transaction was in
        blockNumber (BlockNumber): Block number where this transaction was in
        from (HexStr): Address of the sender
        to (Optional[HexStr]): Address of the receiver. null when its a contract creation
        status (int): Either 1 (success) or 0 (failure)
        contractAddress (Optional[HexStr]): The contract address created, if the
            transaction was a contract creation, otherwise null
        logs (List[LogReceipt]): Array of log objects that this transaction generated
    """

    def __init__(
        self,
        l1BlockNumber: int,
        gasUsedForL1: int,
        transactionHash: Hash32,
        transactionIndex: int,
        blockHash: Hash32,
        blockNumber: BlockNumber,
        from_: HexStr,
        to: Optional[HexStr],
        status: int,
        contractAddress: Optional[HexStr],
        logs: List[LogReceipt],
        **kwargs: Any,
    ) -> None:
        """Initialize a new ArbTransactionReceipt.

        Args:
            l1BlockNumber: L1 block number used for block.number calls
            gasUsedForL1: Gas spent on L1 computation in L2 gas units
            transactionHash: Hash of the transaction
            transactionIndex: Transaction's position in the block
            blockHash: Hash of the containing block
            blockNumber: Number of the containing block
            from_: Address of the sender
            to: Address of the receiver, or None for contract creation
            status: 1 for success, 0 for failure
            contractAddress: Created contract address, or None
            logs: List of event logs generated
            **kwargs: Additional receipt fields to include
        """
        super().__init__(
            transactionHash=transactionHash,
            transactionIndex=transactionIndex,
            blockHash=blockHash,
            blockNumber=blockNumber,
            from_=from_,
            to=to,
            status=status,
            contractAddress=contractAddress,
            logs=logs,
            **kwargs
        )
        self.l1BlockNumber = l1BlockNumber
        self.gasUsedForL1 = gasUsedForL1
