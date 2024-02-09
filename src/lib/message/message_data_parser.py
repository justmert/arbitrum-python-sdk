from eth_abi import decode
from web3 import Web3

from src.lib.utils.helper import CaseDict


class SubmitRetryableMessageDataParser:
    @staticmethod
    def parse(event_data):
        if isinstance(event_data, bytes):
            event_data = event_data.hex()

        if isinstance(event_data, str):
            decoded_data = decode(
                [
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                ],
                Web3.to_bytes(hexstr=event_data),
            )
        else:
            decoded_data = decode(
                [
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint256",
                ],
                event_data,
            )

        def address_from_big_number(bn):
            return Web3.to_checksum_address(bn.to_bytes(20, byteorder="big"))

        dest_address = address_from_big_number(decoded_data[0])
        l2_call_value = decoded_data[1]
        l1_value = decoded_data[2]
        max_submission_fee = decoded_data[3]
        excess_fee_refund_address = address_from_big_number(decoded_data[4])
        call_value_refund_address = address_from_big_number(decoded_data[5])
        gas_limit = decoded_data[6]
        max_fee_per_gas = decoded_data[7]
        call_data_length = decoded_data[8]

        if isinstance(event_data, str):
            data_offset = len(event_data) - 2 * call_data_length
            data = "0x" + event_data[data_offset:]
        else:
            data_length_chars = call_data_length
            data_bytes = event_data[-data_length_chars:]
            data = "0x" + data_bytes.hex()

        return CaseDict(
            {
                "destAddress": dest_address,
                "l2CallValue": l2_call_value,
                "l1Value": l1_value,
                "maxSubmissionFee": max_submission_fee,
                "excessFeeRefundAddress": excess_fee_refund_address,
                "callValueRefundAddress": call_value_refund_address,
                "gasLimit": gas_limit,
                "maxFeePerGas": max_fee_per_gas,
                "data": data,
            }
        )
