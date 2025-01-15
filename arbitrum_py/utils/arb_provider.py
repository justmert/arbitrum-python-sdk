from typing import Any, Dict, Optional, Union

from arbitrum_py.data_entities.rpc import (
    ArbBlock,
    ArbBlockWithTransactions,
    ArbTransactionReceipt,
)
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider


class ArbFormatter:
    """
    A formatter class for Arbitrum-specific data structures.

    This class provides methods for formatting blocks and transaction receipts
    to include Arbitrum-specific fields. It is the Python equivalent of the
    TypeScript ArbFormatter class.

    The formatter handles the following Arbitrum-specific fields:
        - sendRoot: Hash of the send root
        - sendCount: Number of messages sent
        - l1BlockNumber: L1 block number reference
        - gasUsedForL1: Gas used for L1 posting (in receipts)
    """

    def receipt(self, value: Dict[str, Any]) -> ArbTransactionReceipt:
        """
        Format a raw transaction receipt into an ArbTransactionReceipt.

        Adds Arbitrum-specific fields to the standard transaction receipt:
        - l1BlockNumber: The referenced L1 block number
        - gasUsedForL1: Amount of gas used for L1 posting

        :param value: Raw receipt data from a node
        :type value: Dict[str, Any]
        :return: Formatted receipt with Arbitrum-specific fields
        :rtype: ArbTransactionReceipt
        """
        formatted_value = {
            **value,
            "l1BlockNumber": value.get("l1BlockNumber", 0),
            "gasUsedForL1": value.get("gasUsedForL1", 0),
        }
        return ArbTransactionReceipt(**formatted_value)

    def block(self, block: Dict[str, Any]) -> ArbBlock:
        """
        Format a raw block into an ArbBlock.

        Adds Arbitrum-specific fields to the standard block:
        - sendRoot: Hash of the send root
        - sendCount: Number of messages sent
        - l1BlockNumber: Referenced L1 block number

        :param block: Raw block data from the node
        :type block: Dict[str, Any]
        :return: Formatted block with Arbitrum-specific fields
        :rtype: ArbBlock
        """
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot"),
            "sendCount": block.get("sendCount"),
            "l1BlockNumber": block.get("l1BlockNumber"),
        }
        return ArbBlock(**formatted_block)

    def block_with_transactions(self, block: Dict[str, Any]) -> ArbBlockWithTransactions:
        """
        Format a raw block (including full transactions) into an ArbBlockWithTransactions.

        Similar to block(), but includes complete transaction objects rather than
        just transaction hashes.

        :param block: Raw block data including full transaction objects
        :type block: Dict[str, Any]
        :return: Formatted block with transactions and Arbitrum-specific fields
        :rtype: ArbBlockWithTransactions
        """
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot"),
            "sendCount": block.get("sendCount"),
            "l1BlockNumber": block.get("l1BlockNumber"),
        }
        return ArbBlockWithTransactions(**formatted_block)


class ArbitrumProvider:
    """
    An Arbitrum-aware provider that wraps a Web3 provider.

    This class extends the functionality of a standard Web3 provider to handle
    Arbitrum-specific data structures and formatting. It automatically formats
    blocks and receipts to include Arbitrum-specific fields.

    :param provider: The underlying provider to wrap
    :type provider: Union[SignerOrProvider, 'ArbitrumProvider', Any]
    :param network: Optional network configuration (currently unused)
    :type network: Optional[Any]
    """

    def __init__(
        self,
        provider: Union[SignerOrProvider, "ArbitrumProvider", Any],
        network: Optional[Any] = None,
    ):
        if isinstance(provider, SignerOrProvider):
            provider = provider.provider
        elif isinstance(provider, ArbitrumProvider):
            provider = provider._provider

        self._provider = provider
        self.formatter = ArbFormatter()

    @property
    def provider(self) -> Any:
        """
        Get the underlying provider instance.

        :return: The wrapped provider instance
        :rtype: Any
        """
        return self._provider

    def get_transaction_receipt(self, transaction_hash: str) -> ArbTransactionReceipt:
        """
        Get and format a transaction receipt with Arbitrum-specific fields.

        :param transaction_hash: The transaction hash to fetch
        :type transaction_hash: str
        :return: Transaction receipt with Arbitrum-specific fields
        :rtype: ArbTransactionReceipt
        """
        receipt = self._provider.eth.get_transaction_receipt(transaction_hash)
        return self.formatter.receipt(receipt)

    def get_block_with_transactions(self, block_identifier: Union[str, int]) -> ArbBlockWithTransactions:
        """
        Get and format a block (including transactions) with Arbitrum-specific fields.

        :param block_identifier: Block identifier (number, hash, or tag like 'latest')
        :type block_identifier: Union[str, int]
        :return: Block with full transactions and Arbitrum-specific fields
        :rtype: ArbBlockWithTransactions
        """
        block = self._provider.eth.get_block(block_identifier, full_transactions=True)
        return self.formatter.block_with_transactions(block)

    def get_block(self, block_identifier: Union[str, int]) -> ArbBlock:
        """
        Get and format a block with Arbitrum-specific fields.

        :param block_identifier: Block identifier (number, hash, or tag like 'latest')
        :type block_identifier: Union[str, int]
        :return: Block with Arbitrum-specific fields
        :rtype: ArbBlock
        """
        block = self._provider.eth.get_block(block_identifier)
        return self.formatter.block(block)
