from web3 import Web3
from decimal import Decimal
from typing import Dict, Optional, Union
import json

class RetryableData:
    """
    Equivalent of TypeScript's RetryableData interface
    """
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
    def try_parse_error(error_or_data: Union[Exception, Dict[str, str], str]) -> Optional[RetryableData]:
        error_data = None

        if isinstance(error_or_data, str):
            error_data = error_or_data
        elif isinstance(error_or_data, dict) and 'errorData' in error_or_data:
            error_data = error_or_data['errorData']
        elif isinstance(error_or_data, Exception):
            # Extract error data from exception
            pass  # Implement based on the structure of your exceptions

        if error_data:
            return RetryableDataTools.parse_error_data(error_data)
        return None

    @staticmethod
    def parse_error_data(error_data: str) -> Optional[RetryableData]:
        try:
            # due to limitations in the ABI encoding, we can't decode the error data directly            
            # Extract the relevant fields from parsed_error to create a RetryableData instance
            return RetryableData(**error_data)
        except Exception as e:
            # Handle decoding error
            return None
    