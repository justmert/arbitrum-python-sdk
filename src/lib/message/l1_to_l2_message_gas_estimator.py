from web3 import Web3
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
import json
from src.lib.data_entities.errors import ArbSdkError
from src.lib.utils.lib import get_base_fee
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.utils.helper import load_contract


# Constants and imports for BigNumber handling, error classes, etc.
DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE = Decimal(300)
DEFAULT_GAS_PRICE_PERCENT_INCREASE = Decimal(200)

class L1ToL2MessageGasEstimator:
    def __init__(self, l2_provider_url):
        self.w3 = Web3(Web3.HTTPProvider(l2_provider_url))

    def percent_increase(self, num: Decimal, increase: Decimal) -> Decimal:
        return num + num * increase / Decimal(100)


    async def estimate_submission_fee(
        self, l1_provider: Web3, l1_base_fee: Decimal, call_data_size: int, 
        options: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        # Apply default options if necessary
        options = options or {}
        percent_increase = options.get("percentIncrease", DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE)

        inbox = load_contract("Inbox", NODE_INTERFACE_ADDRESS, self.w3)  # Update with actual inbox address
        submission_fee = inbox.functions.calculateRetryableSubmissionFee(call_data_size, l1_base_fee).call()

        return self.percent_increase(Decimal(submission_fee), percent_increase)

    async def estimate_retryable_ticket_gas_limit(
        self, retryable_data: Dict[str, Any], sender_deposit: Decimal = Decimal('1')
    ) -> Decimal:
        node_interface = self.load_contract("NodeInterface", NODE_INTERFACE_ADDRESS, self.w3)
        gas_limit = node_interface.functions.estimateRetryableTicket(
            retryable_data['from'],
            sender_deposit,
            retryable_data['to'],
            retryable_data['l2CallValue'],
            retryable_data['excessFeeRefundAddress'],
            retryable_data['callValueRefundAddress'],
            retryable_data['data']
        ).call()
        return Decimal(gas_limit)

    async def estimate_max_fee_per_gas(
        self, options: Optional[Dict[str, Decimal]] = None
    ) -> Decimal:
        options = options or {}
        percent_increase = options.get("percentIncrease", DEFAULT_GAS_PRICE_PERCENT_INCREASE)
        gas_price = self.w3.eth.gas_price
        return self.percent_increase(Decimal(gas_price), percent_increase)

    async def estimate_all(self, retryable_estimate_data: Dict[str, Any], l1_base_fee: Decimal, 
                           l1_provider: Web3, options: Optional[Dict[str, Any]] = None) -> Dict[str, Decimal]:
        data = retryable_estimate_data['data']
        gas_limit_options = options.get('gasLimit', {}) if options else {}
        max_fee_per_gas_options = options.get('maxFeePerGas', {}) if options else {}
        max_submission_fee_options = options.get('maxSubmissionFee', {}) if options else {}

        # Estimate max fee per gas
        max_fee_per_gas_estimate = await self.estimate_max_fee_per_gas(max_fee_per_gas_options)

        # Estimate submission fee
        max_submission_fee_estimate = await self.estimate_submission_fee(
            l1_provider, l1_base_fee, len(data), max_submission_fee_options
        )

        # Estimate gas limit
        estimated_gas_limit = await self.estimate_retryable_ticket_gas_limit(retryable_estimate_data)

        deposit = options.get('deposit', {}).get('base', Decimal(0)) or \
                  estimated_gas_limit * max_fee_per_gas_estimate + max_submission_fee_estimate

        return {
            'gasLimit': estimated_gas_limit,
            'maxFeePerGas': max_fee_per_gas_estimate,
            'maxSubmissionCost': max_submission_fee_estimate,
            'deposit': deposit
        }

    async def populate_function_params(self, data_func, l1_provider: Web3, gas_overrides: Optional[Dict[str, Any]] = None):
        # Dummy values to trigger a special revert containing the real params
        dummy_params = {
            'gasLimit': Decimal(0),
            'maxFeePerGas': Decimal(0),
            'maxSubmissionCost': Decimal(1)
        }
        tx_request_dummy = data_func(dummy_params)
        
        # Attempt to get retryable data from null call
        try:
            null_call_result = l1_provider.eth.call({
                'to': tx_request_dummy['to'],
                'data': tx_request_dummy['data'],
                'value': tx_request_dummy['value'],
                'from': tx_request_dummy['from']
            })
            retryable = self.parse_retryable_data(null_call_result)
        except Exception as e:
            retryable = self.parse_retryable_data(str(e))

        if not retryable:
            raise ArbSdkError('No retryable data found in error')

        # Use retryable data to get gas estimates
        base_fee = await get_base_fee(l1_provider)
        estimates = await self.estimate_all(retryable, base_fee, l1_provider, gas_overrides)

        # Real data for the transaction
        real_params = {
            'gasLimit': estimates['gasLimit'],
            'maxFeePerGas': estimates['maxFeePerGas'],
            'maxSubmissionCost': estimates['maxSubmissionCost']
        }
        tx_request_real = data_func(real_params)

        return {
            'estimates': estimates,
            'retryable': retryable,
            'data': tx_request_real['data'],
            'to': tx_request_real['to'],
            'value': tx_request_real['value']
        }
        