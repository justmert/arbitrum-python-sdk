from web3 import Web3
from web3.middleware import geth_poa_middleware
from src.lib.data_entities.rpc import ArbBlock, ArbBlockWithTransactions, ArbTransactionReceipt

class ArbFormatter:
    def receipt(self, value):
        # Transform the receipt data as needed
        return ArbTransactionReceipt(**value)

    def block(self, block):
        # Transform the block data as needed
        print(block)
        return ArbBlock(**block)

    def block_with_transactions(self, block):
        # Transform the block data with transactions as needed
        return ArbBlockWithTransactions(**block)

class ArbitrumProvider:
    def __init__(self, provider, network=None):
        self.w3 = provider
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.formatter = ArbFormatter()

    async def get_transaction_receipt(self, transaction_hash):
        receipt = self.w3.eth.get_transaction_receipt(transaction_hash)
        return self.formatter.receipt(receipt)

    async def get_block_with_transactions(self, block_identifier):
        block = self.w3.eth.get_block(block_identifier, full_transactions=True)
        return self.formatter.block_with_transactions(block)

    async def get_block(self, block_identifier):
        block = self.w3.eth.get_block(block_identifier)
        return self.formatter.block(block)
