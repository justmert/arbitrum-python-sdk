from web3 import Web3
# from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
import json
from src.lib.data_entities.errors import ArbSdkError
from src.lib.utils.lib import get_base_fee
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.utils.helper import load_contract
from src.lib.data_entities.retryable_data import RetryableDataTools, RetryableData
from src.lib.data_entities.networks import get_l2_network

# Constants and imports for BigNumber handling, error classes, etc.
DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE = 300
DEFAULT_GAS_PRICE_PERCENT_INCREASE = 200


class L1ToL2MessageGasEstimator:
    def __init__(self, l2_provider_or_url):
        if isinstance(l2_provider_or_url, Web3):
            self.l2_provider = l2_provider_or_url
        else:
            self.l2_provider = Web3(Web3.HTTPProvider(l2_provider_or_url))

    def percent_increase(self, num, increase):
        return num + num * increase / 100

    async def estimate_submission_fee(
        self,
        l1_provider: Web3,
        l1_base_fee,
        call_data_size: int,
        options = None,
    ):
        # Apply default options if necessary
        options = options or {}
        percent_increase = options.get(
            "percentIncrease", DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE
        )
        # const network = await getL2Network(this.l2Provider)
        network = get_l2_network(self.l2_provider)
        inbox = load_contract(
            contract_name="Inbox",
            address=network.ethBridge.inbox,
            provider=l1_provider,
            is_classic=False,
        )  # Update with actual inbox address
        submission_fee = inbox.functions.calculateRetryableSubmissionFee(
            call_data_size, l1_base_fee
        ).call()

        return self.percent_increase(submission_fee, percent_increase)

    async def estimate_retryable_ticket_gas_limit(
        self, retryable_data, sender_deposit = 1
    ):
        sender_deposit_eth = Web3.to_wei(sender_deposit, 'ether') + retryable_data["l2CallValue"]

        node_interface = load_contract(provider=self.l2_provider, contract_name='NodeInterface', address=NODE_INTERFACE_ADDRESS, is_classic=False)

        # Parameters for the estimateRetryableTicket function
        params = {
            "from": retryable_data["from"],
            "to": NODE_INTERFACE_ADDRESS,  # Address of the NodeInterface contract
            "data": node_interface.encodeABI(
                fn_name="estimateRetryableTicket",
                args=[
                    retryable_data["from"],
                    sender_deposit_eth,
                    retryable_data["to"],
                    retryable_data["l2CallValue"],
                    retryable_data["excessFeeRefundAddress"],
                    retryable_data["callValueRefundAddress"],
                    retryable_data["data"]
                ]
            )
        }

        # Estimate the gas
        try:
            gas_estimate = self.l2_provider.eth.estimate_gas(params)
            print("Estimated Gas:", gas_estimate)
        except Exception as e:
            print("Error estimating gas:", e)

        return gas_estimate

    async def estimate_max_fee_per_gas(
        self, options = None
    ) :
        options = options or {}
        percent_increase = options.get(
            "percentIncrease", DEFAULT_GAS_PRICE_PERCENT_INCREASE
        )
        gas_price = self.l2_provider.eth.gas_price
        return self.percent_increase(int(gas_price), percent_increase)

    async def estimate_all(
        self,
        retryable_estimate_data,
        l1_base_fee,
        l1_provider: Web3,
        options = None,
    ):
        options = options or {}
        
        data = retryable_estimate_data["data"]
        gas_limit_options = options.get("gasLimit", {})
        max_fee_per_gas_options = options.get("maxFeePerGas", {})
        max_submission_fee_options = (
            options.get("maxSubmissionFee", {})
        )

        # Estimate max fee per gas
        max_fee_per_gas_estimate = await self.estimate_max_fee_per_gas(
            max_fee_per_gas_options
        )

        # Estimate submission fee
        max_submission_fee_estimate = await self.estimate_submission_fee(
            l1_provider, l1_base_fee, len(data), max_submission_fee_options
        )

        # Estimate gas limit
        estimated_gas_limit = await self.estimate_retryable_ticket_gas_limit(
            retryable_estimate_data
        )

        deposit = (
            options.get("deposit", {}).get("base", 0)
            or estimated_gas_limit * max_fee_per_gas_estimate
            + max_submission_fee_estimate
        )

        return {
            "gasLimit": estimated_gas_limit,
            "maxFeePerGas": max_fee_per_gas_estimate,
            "maxSubmissionCost": max_submission_fee_estimate,
            "deposit": deposit,
        }

    async def populate_function_params(
        self, data_func, l1_provider, gas_overrides=None
    ):
        # Dummy values to trigger a special revert containing the real params
        dummy_params = {
            "gasLimit": 1,
            "maxFeePerGas": 1,
            "maxSubmissionCost": 1,
        }
        null_data_request = data_func(dummy_params)
        retryable_data = None
        try:
            res = await l1_provider.eth.call(null_data_request)
            retryable_data = RetryableDataTools.try_parse_error(str(res))
        except Exception as err:
            if hasattr(err, "data"):
                retryable_data = err.data
                retryable_data = RetryableDataTools.try_parse_error(str(err))

        if retryable_data is None:
            raise ArbSdkError("No retryable data found in error")

        base_fee = await get_base_fee(l1_provider)

        estimates = await self.estimate_all(
            {
                "from": retryable_data["from"],
                "to": retryable_data["to"],
                "data": retryable_data["data"],
                "l2CallValue": retryable_data["l2CallValue"],
                "excessFeeRefundAddress": retryable_data["excessFeeRefundAddress"],
                "callValueRefundAddress": retryable_data["callValueRefundAddress"],
            },
            base_fee,
            l1_provider,
            gas_overrides,
        )

        # Real data for the transaction
        real_params = {
            "gasLimit": estimates["gasLimit"],
            "maxFeePerGas": estimates["maxFeePerGas"],
            "maxSubmissionCost": estimates["maxSubmissionCost"],
        }
        tx_request_real = data_func(real_params)

        return {
            "estimates": estimates,
            "retryable": retryable_data,
            "data": tx_request_real["data"],
            "to": tx_request_real["to"],
            "value": tx_request_real["value"],
        }
