from enum import Enum


class RetryableMessageParams:
    def __init__(
        self,
        dest_address,
        l2_call_value,
        l1_value,
        max_submission_fee,
        excess_fee_refund_address,
        call_value_refund_address,
        gas_limit,
        max_fee_per_gas,
        data,
    ):
        self.dest_address = dest_address
        self.l2_call_value = l2_call_value
        self.l1_value = l1_value
        self.max_submission_fee = max_submission_fee
        self.excess_fee_refund_address = excess_fee_refund_address
        self.call_value_refund_address = call_value_refund_address
        self.gas_limit = gas_limit
        self.max_fee_per_gas = max_fee_per_gas
        self.data = data


class InboxMessageKind(Enum):
    L1MessageType_submitRetryableTx = 9
    L1MessageType_ethDeposit = 12
    L2MessageType_signedTx = 4


class L2ToL1MessageStatus(Enum):
    UNCONFIRMED = 1
    CONFIRMED = 2
    EXECUTED = 3
