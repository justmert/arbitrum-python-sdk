from eth_abi import abi
from web3 import Web3

from src.lib.utils.helper import CaseDict


class RetryableData:
    """
    Equivalent of TypeScript's RetryableData interface
    """

    abi_types = [
        "address",
        "address",
        "uint256",
        "uint256",
        "uint256",
        "address",
        "address",
        "uint256",
        "uint256",
        "bytes",
    ]

    def __init__(
        self,
        from_address,
        to,
        l2_call_value,
        deposit,
        max_submission_cost,
        excess_fee_refund_address,
        call_value_refund_address,
        gas_limit,
        max_fee_per_gas,
        data,
    ):
        self.from_address = from_address
        self.to = to
        self.l2_call_value = l2_call_value
        self.deposit = deposit
        self.max_submission_cost = max_submission_cost
        self.excess_fee_refund_address = excess_fee_refund_address
        self.call_value_refund_address = call_value_refund_address
        self.gas_limit = gas_limit
        self.max_fee_per_gas = max_fee_per_gas
        self.data = data


class RetryableDataTools:
    ErrorTriggeringParams = {
        "gasLimit": 1,
        "maxFeePerGas": 1,
    }

    @staticmethod
    def try_parse_error(
        error_data_hex,
    ):
        try:
            if error_data_hex.startswith("0x"):
                error_data_hex = error_data_hex[2:]
            error_data_hex = error_data_hex[8:]

            decoded_data = abi.decode(RetryableData.abi_types, bytes.fromhex(error_data_hex))

            if len(decoded_data) != len(RetryableData.abi_types):
                return None
            else:
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
                        "data": decoded_data[9],
                    }
                )
        except Exception:
            return None
