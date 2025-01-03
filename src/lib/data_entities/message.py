from enum import Enum


class RetryableMessageParams:
    """
    The components of a submit retryable message (Arbitrum).
    Typically parsed from the events emitted by the Inbox contract 
    on the parent chain when creating a retryable ticket.
    """

    def __init__(
        self,
        dest_address: str,
        l2_call_value: int,
        l1_value: int,
        max_submission_fee: int,
        excess_fee_refund_address: str,
        call_value_refund_address: str,
        gas_limit: int,
        max_fee_per_gas: int,
        data: str,
    ):
        """
        :param dest_address: Destination address for the L2 message
        :param l2_call_value: The call value in the L2 message
        :param l1_value: The total value sent at L1 
                         (usually covers max_submission_fee + execution cost + l2_call_value if ETH-based)
        :param max_submission_fee: The maximum cost to cover the base submission fee on L2
        :param excess_fee_refund_address: The L2 address to credit leftover fees after execution
        :param call_value_refund_address: The L2 address to receive l2CallValue if this message times out/cancelled
        :param gas_limit: The maximum gas used by L2 execution
        :param max_fee_per_gas: The gas price for L2 execution
        :param data: The calldata for the L2 contract function
        """
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
    """
    The message kind for L1<->L2 messages as defined in Arbitrum's
    nitro/contracts/src/libraries/MessageTypes.sol
    """
    L1MessageType_submitRetryableTx = 9
    L1MessageType_ethDeposit = 12
    L2MessageType_signedTx = 4


class ChildToParentMessageStatus(Enum):
    """
    The status of an L2->L1 outgoing message:
    UNCONFIRMED: sendTxToL1 called, but assertion not yet confirmed
    CONFIRMED: assertion confirmed, message not yet executed
    EXECUTED: message has been executed (terminal state)
    """
    UNCONFIRMED = 1
    CONFIRMED = 2
    EXECUTED = 3
