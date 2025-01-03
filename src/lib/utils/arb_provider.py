from web3 import Web3

from src.lib.data_entities.rpc import (
    ArbBlock,
    ArbBlockWithTransactions,
    ArbTransactionReceipt,
)
from src.lib.data_entities.signer_or_provider import SignerOrProvider


class ArbFormatter:
    """
    A Python equivalent of the Arbitrum-specific Formatter in TypeScript.
    Provides methods for formatting blocks and receipts to include 
    Arbitrum-specific fields (e.g. sendRoot, sendCount, l1BlockNumber).
    """

    def receipt(self, value: dict) -> ArbTransactionReceipt:
        """
        Convert a raw transaction receipt dict into an ArbTransactionReceipt with 
        extra Arbitrum fields (l1BlockNumber, gasUsedForL1).

        :param value: Raw receipt data from a node
        :return: ArbTransactionReceipt with additional fields
        """
        formatted_value = {
            **value,
            "l1BlockNumber": value.get("l1BlockNumber", 0),
            "gasUsedForL1": value.get("gasUsedForL1", 0),
        }
        return ArbTransactionReceipt(**formatted_value)

    def block(self, block: dict) -> ArbBlock:
        """
        Convert a raw block dict into an ArbBlock including 
        Arbitrum fields (sendRoot, sendCount, l1BlockNumber).

        :param block: Raw block data
        :return: ArbBlock
        """
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot"),
            "sendCount": block.get("sendCount"),
            "l1BlockNumber": block.get("l1BlockNumber"),
        }
        return ArbBlock(**formatted_block)

    def block_with_transactions(self, block: dict) -> ArbBlockWithTransactions:
        """
        Convert raw block data (with transactions) into an ArbBlockWithTransactions
        containing extra Arbitrum fields.

        :param block: Raw block data including transactions
        :return: ArbBlockWithTransactions
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
    Python equivalent of the TypeScript `ArbitrumProvider extends Web3Provider`.
    This class wraps a standard Web3 provider but returns Arbitrum-formatted 
    blocks and receipts (ArbBlock, ArbTransactionReceipt, etc.).
    """

    def __init__(self, provider, network=None):
        """
        :param provider: Could be a raw Web3 object, or a SignerOrProvider, or another ArbitrumProvider
        :param network: Optional network info (unused in this simplified version)
        """
        if isinstance(provider, SignerOrProvider):
            provider = provider.provider
        elif isinstance(provider, ArbitrumProvider):
            provider = provider.provider

        self.provider = provider
        self.formatter = ArbFormatter()

    async def get_transaction_receipt(self, transaction_hash: str) -> ArbTransactionReceipt:
        """
        Get a transaction receipt from the underlying provider, 
        then format it to an ArbTransactionReceipt.

        :param transaction_hash: The tx hash to fetch
        :return: ArbTransactionReceipt with Arbitrum fields
        """
        receipt = self.provider.eth.get_transaction_receipt(transaction_hash)
        return self.formatter.receipt(receipt)

    async def get_block_with_transactions(self, block_identifier) -> ArbBlockWithTransactions:
        """
        Get a block by number or hash, including full transaction objects,
        then format it to ArbBlockWithTransactions.

        :param block_identifier: e.g. 'latest', a block number, or a block hash
        :return: ArbBlockWithTransactions including Arbitrum fields
        """
        block = self.provider.eth.get_block(
            block_identifier, full_transactions=True
        )
        return self.formatter.block_with_transactions(block)

    async def get_block(self, block_identifier) -> ArbBlock:
        """
        Get a block by number or hash, then format it to ArbBlock.

        :param block_identifier: e.g. 'latest', a block number, or a block hash
        :return: ArbBlock including Arbitrum fields
        """
        block = self.provider.eth.get_block(block_identifier)
        return self.formatter.block(block)
