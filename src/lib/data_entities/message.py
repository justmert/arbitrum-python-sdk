from enum import Enum
from web3 import Web3

class RetryableMessageParams:
    """
    The components of a submit retryable message. Can be parsed from the
    events emitted from the Inbox.
    """
    def __init__(self, dest_address, l2_call_value, l1_value, max_submission_fee,
                 excess_fee_refund_address, call_value_refund_address, gas_limit,
                 max_fee_per_gas, data):
        self.dest_address = dest_address
        self.l2_call_value = Web3.toWei(l2_call_value, 'ether')
        self.l1_value = Web3.toWei(l1_value, 'ether')
        self.max_submission_fee = Web3.toWei(max_submission_fee, 'ether')
        self.excess_fee_refund_address = excess_fee_refund_address
        self.call_value_refund_address = call_value_refund_address
        self.gas_limit = gas_limit
        self.max_fee_per_gas = Web3.toWei(max_fee_per_gas, 'gwei')
        self.data = data

class InboxMessageKind(Enum):
    L1MessageType_submitRetryableTx = 9
    L1MessageType_ethDeposit = 12
    L2MessageType_signedTx = 4

class L2ToL1MessageStatus(Enum):
    UNCONFIRMED = 1
    CONFIRMED = 2
    EXECUTED = 3
