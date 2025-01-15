from typing import Any, Dict, TypedDict
from eth_typing import HexStr


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


class ArbBlock(Dict[str, Any]):
    """An Arbitrum block combining standard Ethereum and Arbitrum-specific fields.

    This class merges standard Web3 block data (Web3Block) with Arbitrum-specific
    fields (ArbBlockProps). It provides a complete view of an Arbitrum block
    including both L1 and L2 relevant information.

    Inherits all fields from Web3Block (standard Ethereum block fields) plus:
        - All fields from ArbBlockProps
    """

    def __init__(self, block_data: Dict[str, Any]):
        super().__init__()
        # Copy Web3Block fields
        for key, value in block_data.items():
            self[key] = value

        # Ensure Arbitrum-specific fields are present
        if not all(hasattr(self, field) for field in ["sendRoot", "sendCount", "l1BlockNumber"]):
            raise ValueError("Missing required Arbitrum block fields")


class ArbBlockWithTransactions(ArbBlock):
    """An Arbitrum block that includes full transaction objects.

    Similar to ethers.js BlockWithTransactions, this class includes the full
    transaction objects rather than just transaction hashes. Useful when you
    need detailed transaction data along with the block data.

    Attributes:
        transactions (List[TxData]): List of full transaction objects included
            in this block
    """

    def __init__(self, block_data: Dict[str, Any]):
        super().__init__(block_data)
        if "transactions" not in self:
            raise ValueError("Missing transactions field in block data")
        if not isinstance(self["transactions"], list):
            raise ValueError("Transactions field must be a list")


class ArbTransactionReceipt(Dict[str, Any]):
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
        from_ (HexStr): Address of the sender
        to (Optional[HexStr]): Address of the receiver. null when its a contract creation
        status (int): Either 1 (success) or 0 (failure)
        contractAddress (Optional[HexStr]): The contract address created, if the
            transaction was a contract creation, otherwise null
        logs (List[LogReceipt]): Array of log objects that this transaction generated
    """

    def __init__(self, receipt_data: Dict[str, Any]):
        super().__init__()
        # Copy standard receipt fields
        for key, value in receipt_data.items():
            if key == "from":
                self["from_"] = value  # Handle Python keyword
            else:
                self[key] = value

        # Ensure Arbitrum-specific fields are present
        if not all(field in self for field in ["l1BlockNumber", "gasUsedForL1"]):
            raise ValueError("Missing required Arbitrum transaction receipt fields")
