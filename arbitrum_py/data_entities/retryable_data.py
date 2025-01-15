from typing import Dict, List, Optional

from eth_abi import abi
from eth_typing import HexAddress, HexStr
from web3 import Web3

from arbitrum_py.utils.helper import CaseDict


class RetryableData:
    """Represents a retryable ticket's data structure on Arbitrum.

    This class mirrors the RetryableData error struct from Inbox.sol and contains
    all parameters needed to create or estimate a retryable ticket transaction.

    Attributes:
        fromAddress (HexAddress): The L1 address creating the retryable ticket
        to (HexAddress): Destination address on L2
        l2CallValue (int): The amount of ETH (or token) supplied on L2
        deposit (int): The total deposit on L1 covering L2 gas + L2 call value
        maxSubmissionCost (int): The base submission fee for sending the message
        excessFeeRefundAddress (HexAddress): L2 address for any leftover gas funds
        callValueRefundAddress (HexAddress): L2 address for leftover callValue if canceled
        gasLimit (int): The L2 gas limit for execution
        maxFeePerGas (int): The max L2 gas price
        data (bytes): The calldata for the L2 contract call
    """

    # Types expected in the custom error's signature, in order
    abi_types: List[str] = [
        "address",  # from
        "address",  # to
        "uint256",  # l2CallValue
        "uint256",  # deposit
        "uint256",  # maxSubmissionCost
        "address",  # excessFeeRefundAddress
        "address",  # callValueRefundAddress
        "uint256",  # gasLimit
        "uint256",  # maxFeePerGas
        "bytes",  # data
    ]

    def __init__(
        self,
        from_address: HexAddress,
        to: HexAddress,
        l2_call_value: int,
        deposit: int,
        max_submission_cost: int,
        excess_fee_refund_address: HexAddress,
        call_value_refund_address: HexAddress,
        gas_limit: int,
        max_fee_per_gas: int,
        data: bytes,
    ) -> None:
        """Initialize a new RetryableData instance.

        Args:
            from_address: The L1 address creating the retryable ticket
            to: Destination address on L2
            l2_call_value: The amount of ETH (or token) supplied on L2
            deposit: The total deposit on L1 covering L2 gas + L2 call value
            max_submission_cost: The base submission fee for sending the message
            excess_fee_refund_address: L2 address for any leftover gas funds
            call_value_refund_address: L2 address for leftover callValue if canceled
            gas_limit: The L2 gas limit for execution
            max_fee_per_gas: The max L2 gas price
            data: The calldata for the L2 contract call
        """
        self.fromAddress = from_address
        self.to = to
        self.l2CallValue = l2_call_value
        self.deposit = deposit
        self.maxSubmissionCost = max_submission_cost
        self.excessFeeRefundAddress = excess_fee_refund_address
        self.callValueRefundAddress = call_value_refund_address
        self.gasLimit = gas_limit
        self.maxFeePerGas = max_fee_per_gas
        self.data = data


class RetryableDataTools:
    """Tools for parsing retryable data from revert errors.

    When calling createRetryableTicket on Inbox.sol, special values can be passed
    for gasLimit and maxFeePerGas. This causes the call to revert with the info
    needed to estimate the gas needed for a retryable ticket.

    Attributes:
        ErrorTriggeringParams (Dict[str, int]): Parameters that should be passed
            to createRetryableTicket to induce a revert with retryable data.
            Contains gasLimit=1 and maxFeePerGas=1.
    """

    ErrorTriggeringParams: Dict[str, int] = {
        "gasLimit": 1,
        "maxFeePerGas": 1,
    }

    @staticmethod
    def try_parse_error(error_data_hex: HexStr) -> Optional[CaseDict]:
        """Parse RetryableData struct from revert error data.

        Attempts to parse a RetryableData struct from the given hex string.
        The input should be the revert data from a transaction that reverts
        with `error RetryableData(...)`.

        Args:
            error_data_hex: The raw revert data as a hex string (with or
                without '0x' prefix)

        Returns:
            A CaseDict containing the parsed RetryableData fields if successful,
            or None if parsing fails. The returned dict will have the following
            fields:
                - from (HexAddress): The L1 sender address
                - to (HexAddress): The L2 destination address
                - l2CallValue (int): Amount of ETH/tokens for L2
                - deposit (int): Total L1 deposit amount
                - maxSubmissionCost (int): Base submission fee
                - excessFeeRefundAddress (HexAddress): Refund address for excess gas
                - callValueRefundAddress (HexAddress): Refund address for call value
                - gasLimit (int): L2 gas limit
                - maxFeePerGas (int): Max L2 gas price
                - data (bytes): L2 call data

        Example:
            >>> error_data = "0x..."  # Revert data from failed tx
            >>> retryable = RetryableDataTools.try_parse_error(error_data)
            >>> if retryable:
            ...     print(f"L2 destination: {retryable['to']}")
            ...     print(f"Gas limit: {retryable['gasLimit']}")
        """
        try:
            # Ensure we strip '0x' if present
            if error_data_hex.startswith("0x"):
                error_data_hex = error_data_hex[2:]

            # The first 4 bytes (8 hex digits) in the revert data is the error selector
            # We skip those to decode the actual parameters
            error_data_hex = error_data_hex[8:]

            # Decode the raw hex into the 10 fields
            decoded_data = abi.decode(RetryableData.abi_types, bytes.fromhex(error_data_hex))
            if len(decoded_data) != len(RetryableData.abi_types):
                # Something is off with the length
                return None

            # Build a dictionary that matches the TS 'RetryableData' shape
            # Use checksummed addresses for 'from', 'to', etc.
            return CaseDict(
                {
                    "from": Web3.to_checksum_address(decoded_data[0]),
                    "to": Web3.to_checksum_address(decoded_data[1]),
                    "l2CallValue": decoded_data[2],
                    "deposit": decoded_data[3],
                    "maxSubmissionCost": decoded_data[4],
                    "excessFeeRefundAddress": Web3.to_checksum_address(decoded_data[5]),
                    "callValueRefundAddress": Web3.to_checksum_address(decoded_data[6]),
                    "gasLimit": decoded_data[7],
                    "maxFeePerGas": decoded_data[8],
                    "data": decoded_data[9],  # bytes
                }
            )
        except Exception as e:
            # Return None if we fail to decode
            return None
