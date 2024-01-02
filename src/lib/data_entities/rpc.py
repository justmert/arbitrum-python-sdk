from web3.types import TxReceipt

class ArbBlockProps:
    def __init__(self, send_root: str, send_count: int, l1_block_number: int):
        self.send_root = send_root
        self.send_count = send_count
        self.l1_block_number = l1_block_number

class ArbBlock(ArbBlockProps):
    def __init__(self, send_root: str, send_count: int, l1_block_number: int, block_data):
        super().__init__(send_root, send_count, l1_block_number)
        self.block_data = block_data

class ArbBlockWithTransactions(ArbBlockProps):
    def __init__(self, send_root: str, send_count: int, l1_block_number: int, block_data_with_tx):
        super().__init__(send_root, send_count, l1_block_number)
        self.block_data_with_tx = block_data_with_tx

class ArbTransactionReceipt:
    def __init__(self, tx_receipt: TxReceipt, l1_block_number: int, gas_used_for_l1: int):
        self.tx_receipt = tx_receipt
        self.l1_block_number = l1_block_number
        self.gas_used_for_l1 = gas_used_for_l1
