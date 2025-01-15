"""Message data entities for Arbitrum SDK.

This module defines the data structures and enums used for handling messages
between L1 and L2 chains in the Arbitrum protocol.
"""

from dataclasses import dataclass
from enum import Enum, auto

from eth_typing import HexStr
from web3.types import Wei


@dataclass
class RetryableMessageParams:
    """The components of a submit retryable message.

    This class represents the parameters needed to create a retryable ticket
    on Arbitrum's L2. These parameters are typically parsed from events emitted
    by the Inbox contract on L1.

    Attributes:
        destAddress: Destination address for L2 message
        l2CallValue: Call value in L2 message
        l1Value: Value sent at L1
        maxSubmissionFee: Max gas deducted from L2 balance to cover base submission fee
        excessFeeRefundAddress: L2 address to credit (gaslimit x gasprice - execution cost)
        callValueRefundAddress: Address to credit l2CallValue on L2 if retryable txn
            times out or gets cancelled
        gasLimit: Max gas deducted from user's L2 balance to cover L2 execution
        maxFeePerGas: Gas price for L2 execution
        data: Calldata for the L2 message
    """

    destAddress: HexStr
    l2CallValue: Wei
    l1Value: Wei
    maxSubmissionFee: Wei
    excessFeeRefundAddress: HexStr
    callValueRefundAddress: HexStr
    gasLimit: Wei
    maxFeePerGas: Wei
    data: HexStr

    def __post_init__(self) -> None:
        """Validate and convert input types after initialization."""
        # Convert address strings to checksum format
        from web3 import Web3

        self.destAddress = Web3.to_checksum_address(self.destAddress)
        self.excessFeeRefundAddress = Web3.to_checksum_address(self.excessFeeRefundAddress)
        self.callValueRefundAddress = Web3.to_checksum_address(self.callValueRefundAddress)

        # Ensure Wei values are integers
        self.l2CallValue = Wei(int(self.l2CallValue))
        self.l1Value = Wei(int(self.l1Value))
        self.maxSubmissionFee = Wei(int(self.maxSubmissionFee))
        self.gasLimit = Wei(int(self.gasLimit))
        self.maxFeePerGas = Wei(int(self.maxFeePerGas))

        # # Ensure data is hex string
        # if not self.data.startswith('0x'):
        #     self.data = HexStr('0x' + self.data)


class InboxMessageKind(Enum):
    """The inbox message kind for L1<->L2 messages.

    These values are defined in the Arbitrum Nitro protocol at:
    https://github.com/OffchainLabs/nitro/blob/master/contracts/src/libraries/MessageTypes.sol

    Attributes:
        L1MessageType_submitRetryableTx: Represents a retryable ticket submission (value: 9)
        L1MessageType_ethDeposit: Represents an ETH deposit from L1 to L2 (value: 12)
        L2MessageType_signedTx: Represents a signed transaction on L2 (value: 4)
    """

    L1MessageType_submitRetryableTx = 9
    L1MessageType_ethDeposit = 12
    L2MessageType_signedTx = 4


class ChildToParentMessageStatus(Enum):
    """Status of an L2->L1 outgoing message.

    This enum represents the possible states of a message sent from L2 to L1
    through ArbSys.sendTxToL1.

    Attributes:
        UNCONFIRMED: ArbSys.sendTxToL1 called, but assertion not yet confirmed
        CONFIRMED: Assertion for outgoing message confirmed, but message not yet executed
        EXECUTED: Outgoing message executed (terminal state)
    """

    UNCONFIRMED = auto()
    CONFIRMED = auto()
    EXECUTED = auto()
