from web3 import Web3
from decimal import Decimal
from typing import Dict, Optional, Union
import json
import re
from eth_abi import abi

from test import CaseDict

class RetryableData:
    """
    Equivalent of TypeScript's RetryableData interface
    """

    abi_types = ['address', 'address', 'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256', 'uint256', 'bytes']
    
    def __init__(self, from_address: str, to: str, l2_call_value: Decimal, deposit: Decimal,
                 max_submission_cost: Decimal, excess_fee_refund_address: str,
                 call_value_refund_address: str, gas_limit: Decimal, max_fee_per_gas: Decimal, data: str):
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
    """
    Tools for parsing retryable data from errors.
    """
    ErrorTriggeringParams = {
        'gasLimit': 1,
        'maxFeePerGas': 1,
    }

    @staticmethod
    def try_parse_error(error_data_hex: Union[Exception, Dict[str, str], str]) -> Optional[RetryableData]:
        try:
            if error_data_hex.startswith("0x"):
                error_data_hex = error_data_hex[2:]
            error_data_hex = error_data_hex[8:]

            # Decode the error data
            decoded_data = abi.decode(RetryableData.abi_types, bytes.fromhex(error_data_hex))

            if len(decoded_data) != len(RetryableData.abi_types):
                print('Error decoding retryable data')
                return None
            else:
                return {
                    'from': Web3.to_checksum_address(decoded_data[0]),
                    'to': Web3.to_checksum_address(decoded_data[1]),
                    'l2CallValue': decoded_data[2],
                    'deposit': decoded_data[3],
                    'maxSubmissionCost': decoded_data[4],
                    'excessFeeRefundAddress': Web3.to_checksum_address(decoded_data[5]),
                    'callValueRefundAddress': Web3.to_checksum_address(decoded_data[6]),
                    'gasLimit': decoded_data[7],
                    'maxFeePerGas': decoded_data[8],
                    # 'data': decoded_data[9].hex()  if str(decoded_data[9].hex()).startswith('0x')  else '0x' + decoded_data[9].hex()
                    'data': decoded_data[9]
                }
        except Exception as ex:
            return None

    @staticmethod
    def parse_error_data(error_data: str) -> Optional[RetryableData]:
        if False:
            try:
                # due to limitations in the ABI encoding, we can't decode the error data directly            
                # Extract the relevant fields from parsed_error to create a RetryableData instance
                return RetryableData(**error_data)
            except Exception as e:
                # Handle decoding error
                return None
        return error_data # No need to parse error data