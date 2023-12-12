from web3 import Web3
from eth_utils import to_checksum_address, big_endian_to_int


class SubmitRetryableMessageDataParser:
    """
    Parse the event data emitted in the InboxMessageDelivered event
    for messages of type L1MessageType_submitRetryableTx
    """
    @staticmethod
    def parse(event_data):
        # Assuming event_data is a hex string
        decoded_data = Web3.solidity_decode(
            [
                'uint256',  # dest
                'uint256',  # l2 call value
                'uint256',  # msg val
                'uint256',  # max submission
                'uint256',  # excess fee refund addr
                'uint256',  # call value refund addr
                'uint256',  # max gas
                'uint256',  # gas price bid
                'uint256',  # data length
            ],
            event_data
        )

        def address_from_big_number(bn):
            # Convert BigNumber to address
            return to_checksum_address(bn.to_bytes(20, byteorder='big'))

        dest_address = address_from_big_number(decoded_data[0])
        l2_call_value = decoded_data[1]
        l1_value = decoded_data[2]
        max_submission_fee = decoded_data[3]
        excess_fee_refund_address = address_from_big_number(decoded_data[4])
        call_value_refund_address = address_from_big_number(decoded_data[5])
        gas_limit = decoded_data[6]
        max_fee_per_gas = decoded_data[7]
        call_data_length = decoded_data[8]

        # Extracting call data
        data = '0x' + event_data[-call_data_length * 2:]

        return {
            'destAddress': dest_address,
            'l2CallValue': l2_call_value,
            'l1Value': l1_value,
            'maxSubmissionFee': max_submission_fee,
            'excessFeeRefundAddress': excess_fee_refund_address,
            'callValueRefundAddress': call_value_refund_address,
            'gasLimit': gas_limit,
            'maxFeePerGas': max_fee_per_gas,
            'data': data,
        }
