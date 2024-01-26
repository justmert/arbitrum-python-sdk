from web3 import Web3
from web3.middleware import geth_poa_middleware
from src.lib.data_entities.rpc import ArbBlock, ArbBlockWithTransactions, ArbTransactionReceipt

class ArbFormatter:
    def receipt(self, value):
        """
        Transform the transaction receipt data as needed.
        """
        # Custom formatting for specific fields
        formatted_value = {
            **value,
            "l1BlockNumber": value.get("l1BlockNumber", 0),
            "gasUsedForL1": value.get("gasUsedForL1", 0)  # Assuming BigNumber equivalent in Python is int
        }
        return ArbTransactionReceipt(**formatted_value)

    def block(self, block):
        """
        Transform the block data as needed.
        """
        # Custom formatting for specific fields
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot", ""),
            "sendCount": block.get("sendCount", 0),  # Assuming BigNumber equivalent in Python is int
            "l1BlockNumber": block.get("l1BlockNumber", 0)
        }
        return ArbBlock(**formatted_block)

    def block_with_transactions(self, block):
        """
        Transform the block data with transactions as needed.
        """
        # Custom formatting for specific fields, similar to block()
        formatted_block = {
            **block,
            "sendRoot": block.get("sendRoot", ""),
            "sendCount": block.get("sendCount", 0),  # Assuming BigNumber equivalent in Python is int
            "l1BlockNumber": block.get("l1BlockNumber", 0)
        }
        return ArbBlockWithTransactions(**formatted_block)

    def hash(self, value):
        # Implement the hash conversion logic here
        return value  # Placeholder

class ArbitrumProvider:
    def __init__(self, provider, network=None):
        self.provider = provider
        # self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
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
