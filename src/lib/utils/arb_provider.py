from src.lib.data_entities.rpc import (
    ArbBlock,
    ArbBlockWithTransactions,
    ArbTransactionReceipt,
)
from src.lib.data_entities.signer_or_provider import SignerOrProvider


class ArbFormatter:
    def receipt(self, value):
        formatted_value = {
            **value,
            "l1BlockNumber": value.get("l1BlockNumber", 0),
            "gasUsedForL1": value.get("gasUsedForL1", 0),
        }
        return ArbTransactionReceipt(**formatted_value)

    def block(self, block):
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot", None),
            "sendCount": block.get("sendCount", None),
            "l1BlockNumber": block.get("l1BlockNumber", None),
        }
        return ArbBlock(**formatted_block)

    def block_with_transactions(self, block):
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot", None),
            "sendCount": block.get("sendCount", None),
            "l1BlockNumber": block.get("l1BlockNumber", None),
        }
        return ArbBlockWithTransactions(**formatted_block)


class ArbitrumProvider:
    def __init__(self, provider, network=None):
        if isinstance(provider, SignerOrProvider):
            provider = provider.provider

        elif isinstance(provider, ArbitrumProvider):
            provider = provider.provider

        self.provider = provider
        self.formatter = ArbFormatter()

    async def get_transaction_receipt(self, transaction_hash):
        receipt = self.provider.eth.get_transaction_receipt(transaction_hash)
        return self.formatter.receipt(receipt)

    async def get_block_with_transactions(self, block_identifier):
        block = self.provider.eth.get_block(block_identifier, full_transactions=True)
        return self.formatter.block_with_transactions(block)

    async def get_block(self, block_identifier):
        block = self.provider.eth.get_block(block_identifier)
        return self.formatter.block(block)
