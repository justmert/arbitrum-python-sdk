from eth_abi import abi
from web3 import Web3

from src.lib.utils.helper import CaseDict


class RetryableData:
    """
    Python representation of the TypeScript `RetryableData` interface.

    This structure is often embedded in revert data when calling `createRetryableTicket`
    on `Inbox.sol` with special triggering parameters. 
    It contains the info needed to reconstruct a retryable ticket on Arbitrum.
    """

    # Types expected in the custom error's signature, in order
    abi_types = [
        "address",  # from
        "address",  # to
        "uint256",  # l2CallValue
        "uint256",  # deposit
        "uint256",  # maxSubmissionCost
        "address",  # excessFeeRefundAddress
        "address",  # callValueRefundAddress
        "uint256",  # gasLimit
        "uint256",  # maxFeePerGas
        "bytes",    # data
    ]

    def __init__(
        self,
        from_address: str,
        to: str,
        l2_call_value: int,
        deposit: int,
        max_submission_cost: int,
        excess_fee_refund_address: str,
        call_value_refund_address: str,
        gas_limit: int,
        max_fee_per_gas: int,
        data: bytes,
    ):
        """
        :param from_address: The L1 address creating the retryable ticket
        :param to: Destination address on L2
        :param l2_call_value: The amount of ETH (or token) supplied on L2
        :param deposit: The total deposit on L1 covering L2 gas + L2 call value
        :param max_submission_cost: The base submission fee for sending the message
        :param excess_fee_refund_address: L2 address for any leftover gas funds
        :param call_value_refund_address: L2 address for leftover callValue if canceled
        :param gas_limit: The L2 gas limit for execution
        :param max_fee_per_gas: The max L2 gas price
        :param data: The calldata (bytes) for the L2 contract call
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
    """
    Tools for parsing or triggering a revert that contains `RetryableData`.
    Allows capturing the parameters from an Ethers.js error or raw revert data.
    """

    # Values that, when passed to createRetryableTicket, will intentionally 
    # revert and embed the RetryableData struct in the revert data.
    ErrorTriggeringParams = {
        "gasLimit": 1,
        "maxFeePerGas": 1,
    }

    @staticmethod
    def try_parse_error(error_data_hex: str):
        """
        Attempt to parse a RetryableData struct from the given hex string.
        The caller is expected to supply the revert data from a transaction 
        that reverts with `error RetryableData(...)`.
        
        :param error_data_hex: The raw revert data as a hex string (with or without '0x' prefix).
        :return: A CaseDict containing the fields, or None if parsing fails.
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
            return CaseDict({
                "from": Web3.to_checksum_address(decoded_data[0]),
                "to": Web3.to_checksum_address(decoded_data[1]),
                "l2CallValue": decoded_data[2],
                "deposit": decoded_data[3],
                "maxSubmissionCost": decoded_data[4],
                "excessFeeRefundAddress": Web3.to_checksum_address(decoded_data[5]),
                "callValueRefundAddress": Web3.to_checksum_address(decoded_data[6]),
                "gasLimit": decoded_data[7],
                "maxFeePerGas": decoded_data[8],
                "data": decoded_data[9],   # bytes
            })
        except Exception:
            # Return None if we fail to decode
            return None
