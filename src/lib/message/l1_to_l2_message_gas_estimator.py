from web3 import Web3

from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.retryable_data import RetryableDataTools
from src.lib.utils.helper import CaseDict, load_contract
from src.lib.utils.lib import get_base_fee, is_defined

DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE = 300
DEFAULT_GAS_PRICE_PERCENT_INCREASE = 200

default_l1_to_l2_message_estimate_options = {
    "maxSubmissionFeePercentIncrease": DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE,
    "gasLimitPercentIncrease": 0,
    "maxFeePerGasPercentIncrease": DEFAULT_GAS_PRICE_PERCENT_INCREASE,
}


class L1ToL2MessageGasEstimator:
    def __init__(self, l2_provider):
        self.l2_provider = l2_provider

    def percent_increase(self, num, increase):
        return num + (num * increase // 100)

    def apply_submission_price_defaults(self, max_submission_fee_options=None):
        base = max_submission_fee_options.get("base") if max_submission_fee_options else None
        percent_increase = (
            max_submission_fee_options["percentIncrease"]
            if max_submission_fee_options and "percentIncrease" in max_submission_fee_options
            else default_l1_to_l2_message_estimate_options["maxSubmissionFeePercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_max_fee_per_gas_defaults(self, max_fee_per_gas_options=None):
        base = max_fee_per_gas_options.get("base") if max_fee_per_gas_options else None
        percent_increase = (
            max_fee_per_gas_options["percentIncrease"]
            if max_fee_per_gas_options and "percentIncrease" in max_fee_per_gas_options
            else default_l1_to_l2_message_estimate_options["maxFeePerGasPercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_gas_limit_defaults(self, gas_limit_defaults=None):
        base = gas_limit_defaults.get("base") if gas_limit_defaults else None
        percent_increase = (
            gas_limit_defaults["percentIncrease"]
            if gas_limit_defaults and "percentIncrease" in gas_limit_defaults
            else default_l1_to_l2_message_estimate_options["gasLimitPercentIncrease"]
        )
        min_gas_limit = gas_limit_defaults["min"] if gas_limit_defaults and "min" in gas_limit_defaults else 0
        return {"base": base, "percentIncrease": percent_increase, "min": min_gas_limit}

    async def estimate_submission_fee(
        self,
        l1_provider,
        l1_base_fee,
        call_data_size,
        options=None,
    ):
        defaulted_options = self.apply_submission_price_defaults(options)
        network = get_l2_network(self.l2_provider)
        inbox = load_contract(
            contract_name="Inbox",
            address=network.ethBridge.inbox,
            provider=l1_provider,
            is_classic=False,
        )

        base = defaulted_options.get("base", None)
        if base is None:
            base = inbox.functions.calculateRetryableSubmissionFee(call_data_size, l1_base_fee).call()

        return self.percent_increase(base, defaulted_options["percentIncrease"])

    async def estimate_retryable_ticket_gas_limit(self, retryable_data, sender_deposit=None):
        if sender_deposit is None:
            sender_deposit = Web3.to_wei(1, "ether") + retryable_data["l2CallValue"]

        node_interface = load_contract(
            provider=self.l2_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            is_classic=False,
        )

        return node_interface.functions.estimateRetryableTicket(
            retryable_data["from"],
            sender_deposit,
            retryable_data["to"],
            retryable_data["l2CallValue"],
            retryable_data["excessFeeRefundAddress"],
            retryable_data["callValueRefundAddress"],
            retryable_data["data"],
        ).estimate_gas()

    async def estimate_max_fee_per_gas(self, options=None):
        if options is None:
            options = {}
        max_fee_per_gas_defaults = self.apply_max_fee_per_gas_defaults(options)

        base = max_fee_per_gas_defaults.get("base", None)
        if base is None:
            base = self.l2_provider.eth.gas_price

        return self.percent_increase(base, max_fee_per_gas_defaults["percentIncrease"])

    @staticmethod
    async def is_valid(estimates, re_estimates):
        return (
            estimates["maxFeePerGas"] >= re_estimates["maxFeePerGas"]
            and estimates["maxSubmissionCost"] >= re_estimates["maxSubmissionCost"]
        )

    async def estimate_all(self, retryable_estimate_data, l1_base_fee, l1_provider, options=None):
        if options is None:
            options = {}

        data = retryable_estimate_data["data"]

        gas_limit_defaults = self.apply_gas_limit_defaults(options.get("gasLimit", {}))

        max_fee_per_gas_estimate = await self.estimate_max_fee_per_gas(options.get("maxFeePerGas", {}))

        max_submission_fee_estimate = await self.estimate_submission_fee(
            l1_provider, l1_base_fee, len(data), options.get("maxSubmissionFee", {})
        )

        base = gas_limit_defaults.get("base", None)
        if base is None:
            base = await self.estimate_retryable_ticket_gas_limit(
                retryable_estimate_data, options.get("deposit", {}).get("base", None)
            )

        calculated_gas_limit = self.percent_increase(base, gas_limit_defaults["percentIncrease"])

        if calculated_gas_limit > gas_limit_defaults.get("min"):
            gas_limit = calculated_gas_limit
        else:
            gas_limit = gas_limit_defaults.get("min")

        deposit = options.get("deposit", {}).get("base", None)
        if deposit is None:
            deposit = (
                gas_limit * max_fee_per_gas_estimate
                + max_submission_fee_estimate
                + retryable_estimate_data.get("l2CallValue")
            )

        return {
            "gasLimit": gas_limit,
            "maxFeePerGas": max_fee_per_gas_estimate,
            "maxSubmissionCost": max_submission_fee_estimate,
            "deposit": deposit,
        }

    async def populate_function_params(self, data_func, l1_provider, gas_overrides=None):
        dummy_params = CaseDict(
            {
                "gasLimit": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
                "maxFeePerGas": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
                "maxSubmissionCost": 1,
            }
        )

        null_data_request = data_func(dummy_params)
        retryable = None

        try:
            res = l1_provider.eth.call(null_data_request)
            retryable = RetryableDataTools.try_parse_error(res)
            if not is_defined(retryable):
                raise ArbSdkError(f"No retryable data found in error: {res}")

        except Exception as err:
            if hasattr(err, "data"):
                retryable = RetryableDataTools.try_parse_error(err.data)

            if not is_defined(retryable):
                raise ArbSdkError(f"No retryable data found in error: {err}")

        base_fee = await get_base_fee(l1_provider)

        estimates = await self.estimate_all(
            {
                "from": retryable["from"],
                "to": retryable["to"],
                "data": retryable["data"],
                "l2CallValue": retryable["l2CallValue"],
                "excessFeeRefundAddress": retryable["excessFeeRefundAddress"],
                "callValueRefundAddress": retryable["callValueRefundAddress"],
            },
            base_fee,
            l1_provider,
            gas_overrides,
        )

        real_params = {
            "gasLimit": estimates["gasLimit"],
            "maxFeePerGas": estimates["maxFeePerGas"],
            "maxSubmissionCost": estimates["maxSubmissionCost"],
        }
        tx_request_real = data_func(real_params)

        return {
            "estimates": estimates,
            "retryable": retryable,
            "data": tx_request_real["data"],
            "to": tx_request_real["to"],
            "value": tx_request_real["value"],
        }
