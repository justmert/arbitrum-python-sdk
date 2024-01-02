from web3 import Web3
from eth_typing import ChecksumAddress
from typing import Callable, Dict, Union

# Define the L1ToL2MessageParams and L1ToL2MessageGasParams based on your actual implementation
class L1ToL2MessageParams:
    pass

class L1ToL2MessageGasParams:
    pass

class L1ToL2TransactionRequest:
    def __init__(self, tx_request, retryable_data):
        self.tx_request = tx_request
        self.retryable_data = retryable_data

    async def is_valid(self):
        # Implement the validity check logic based on your requirements
        pass

class L2ToL1TransactionRequest:
    def __init__(self, tx_request, estimate_l1_gas_limit: Callable):
        self.tx_request = tx_request
        self.estimate_l1_gas_limit = estimate_l1_gas_limit

def is_l1_to_l2_transaction_request(possible_request) -> bool:
    return isinstance(possible_request, L1ToL2TransactionRequest)

def is_l2_to_l1_transaction_request(possible_request) -> bool:
    return isinstance(possible_request, L2ToL1TransactionRequest)
