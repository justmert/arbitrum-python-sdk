from typing import Union

from eth_abi import decode
from web3 import Web3
from web3.types import HexStr

from arbitrum_py.utils.helper import CaseDict


class SubmitRetryableMessageDataParser:
    """
    Parser for retryable message data from InboxMessageDelivered events.

    This class provides functionality to parse event data emitted in InboxMessageDelivered events
    for messages of type L1MessageType_submitRetryableTx. It handles both string and bytes input
    formats and returns a structured representation of the message data.
    """

    @staticmethod
    def parse(event_data: Union[str, bytes]) -> CaseDict:
        """
        Parse the event data from an InboxMessageDelivered event.

        This method decodes the data field in InboxMessageDelivered for messages of kind
        L1MessageType_submitRetryableTx. It handles both hex string and bytes input formats.

        Args:
            event_data: The data field from the InboxMessageDelivered event.
                       Can be either a hex string (with or without '0x' prefix) or bytes.

        Returns:
            CaseDict: A dictionary-like object containing the parsed data with the following fields:
                - destAddress (str): The destination address in checksum format
                - l2CallValue (int): The L2 call value in wei
                - l1Value (int): The L1 value in wei
                - maxSubmissionFee (int): The maximum submission fee in wei
                - excessFeeRefundAddress (str): The address for excess fee refund in checksum format
                - callValueRefundAddress (str): The address for call value refund in checksum format
                - gasLimit (int): The gas limit for the transaction
                - maxFeePerGas (int): The maximum fee per gas in wei
                - data (str): The call data as a hex string with '0x' prefix

        Example:
            >>> parser = SubmitRetryableMessageDataParser()
            >>> event_data = "0x..."  # hex string from event
            >>> result = parser.parse(event_data)
            >>> print(result.destAddress)  # '0x742d35Cc6634C0532925a3b844Bc454e4438f44e'
        """
        # Convert bytes to hex string if needed
        if isinstance(event_data, bytes):
            event_data = event_data.hex()

        # Decode the input data
        if isinstance(event_data, str):
            decoded_data = decode(
                [
                    "uint256",  # dest
                    "uint256",  # l2 call value
                    "uint256",  # msg value
                    "uint256",  # max submission fee
                    "uint256",  # excess fee refund address
                    "uint256",  # call value refund address
                    "uint256",  # max gas
                    "uint256",  # gas price bid
                    "uint256",  # data length
                ],
                Web3.to_bytes(hexstr=event_data),
            )
        else:
            decoded_data = decode(
                [
                    "uint256",  # dest
                    "uint256",  # l2 call value
                    "uint256",  # msg value
                    "uint256",  # max submission fee
                    "uint256",  # excess fee refund address
                    "uint256",  # call value refund address
                    "uint256",  # max gas
                    "uint256",  # gas price bid
                    "uint256",  # data length
                ],
                event_data,
            )

        def address_from_big_number(bn: int) -> HexStr:
            """
            Convert a big number to an Ethereum address.

            Args:
                bn: The big number to convert

            Returns:
                The checksum address
            """
            return Web3.to_checksum_address(bn.to_bytes(20, byteorder="big"))

        # Parse the decoded data
        dest_address = address_from_big_number(decoded_data[0])
        l2_call_value = decoded_data[1]
        l1_value = decoded_data[2]
        max_submission_fee = decoded_data[3]
        excess_fee_refund_address = address_from_big_number(decoded_data[4])
        call_value_refund_address = address_from_big_number(decoded_data[5])
        gas_limit = decoded_data[6]
        max_fee_per_gas = decoded_data[7]
        call_data_length = decoded_data[8]

        # Extract the call data based on input type
        if isinstance(event_data, str):
            data_offset = len(event_data) - 2 * call_data_length
            data = "0x" + event_data[data_offset:]
        else:
            data_length_chars = call_data_length
            data_bytes = event_data[-data_length_chars:]
            data = "0x" + data_bytes.hex()

        # Return the parsed data in a CaseDict
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
