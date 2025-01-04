from web3 import Web3

from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.retryable_data import RetryableDataTools
from src.lib.utils.helper import CaseDict, load_contract
from src.lib.utils.lib import (
    get_base_fee,
    is_defined,
    get_native_token_decimals,
    scale_from_18_decimals_to_native_token_decimals
)
DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE = 300
DEFAULT_GAS_PRICE_PERCENT_INCREASE = 500

default_parent_to_child_message_estimate_options = {
    "maxSubmissionFeePercentIncrease": DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE,
    "gasLimitPercentIncrease": 0,
    "maxFeePerGasPercentIncrease": DEFAULT_GAS_PRICE_PERCENT_INCREASE,
}


class ParentToChildMessageGasEstimator:
    """
    Python equivalent of the updated v4 ParentToChildMessageGasEstimator (formerly L1ToL2MessageGasEstimator).
    Estimates gas parameters (gas limit, maxFeePerGas, maxSubmissionCost, deposit) for sending
    Parent->Child retryable transactions in Arbitrum.
    """

    def __init__(self, child_provider):
        """
        :param child_provider: A web3 provider connected to the child chain
        """
        self.child_provider = child_provider

    def percent_increase(self, num: int, increase: int) -> int:
        """
        Utility function: increases `num` by `increase` percent.
        """
        return num + (num * increase // 100)

    def apply_submission_price_defaults(self, max_submission_fee_options=None):
        base = max_submission_fee_options.get("base") if max_submission_fee_options else None
        percent_increase = (
            max_submission_fee_options["percentIncrease"]
            if max_submission_fee_options and "percentIncrease" in max_submission_fee_options
            else default_parent_to_child_message_estimate_options["maxSubmissionFeePercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_max_fee_per_gas_defaults(self, max_fee_per_gas_options=None):
        base = max_fee_per_gas_options.get("base") if max_fee_per_gas_options else None
        percent_increase = (
            max_fee_per_gas_options["percentIncrease"]
            if max_fee_per_gas_options and "percentIncrease" in max_fee_per_gas_options
            else default_parent_to_child_message_estimate_options["maxFeePerGasPercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_gas_limit_defaults(self, gas_limit_defaults=None):
        base = gas_limit_defaults.get("base") if gas_limit_defaults else None
        percent_increase = (
            gas_limit_defaults["percentIncrease"]
            if gas_limit_defaults and "percentIncrease" in gas_limit_defaults
            else default_parent_to_child_message_estimate_options["gasLimitPercentIncrease"]
        )
        min_gas_limit = gas_limit_defaults["min"] if gas_limit_defaults and "min" in gas_limit_defaults else 0
        return {"base": base, "percentIncrease": percent_increase, "min": min_gas_limit}

    async def estimate_submission_fee(
        self,
        parent_provider,
        parent_base_fee: int,
        call_data_size: int,
        options=None,
    ) -> int:
        """
        Return the fee (in wei) of submitting a new retryable transaction with a given call data size.
        This is analogous to `calculateRetryableSubmissionFee(...)`.
        """
        defaulted_options = self.apply_submission_price_defaults(options)
        network = get_arbitrum_network(self.child_provider)

        inbox = load_contract(
            contract_name="Inbox",
            address=network.ethBridge.inbox,
            provider=parent_provider,
            
        )

        # If user did not supply a custom base, fetch from chain
        base = defaulted_options.get("base")
        if base is None:
            base = inbox.functions.calculateRetryableSubmissionFee(call_data_size, parent_base_fee).call()

        return self.percent_increase(base, defaulted_options["percentIncrease"])

    async def estimate_retryable_ticket_gas_limit(self, retryable_data: dict, sender_deposit: int = None) -> int:
        """
        Estimate the child-chain gas required to create and execute a retryable transaction.

        :param retryable_data: {
          "from", "to", "l2CallValue", "excessFeeRefundAddress",
          "callValueRefundAddress", "data"
        }
        :param sender_deposit: The deposit to pass with the transaction (in wei).
        """
        if sender_deposit is None:
            sender_deposit = Web3.to_wei(1, "ether") + retryable_data["l2CallValue"]

        node_interface = load_contract(
            provider=self.child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            
        )

        # estimateGas is used to get the gas limit for NodeInterface.estimateRetryableTicket()
        return node_interface.functions.estimateRetryableTicket(
            retryable_data["from"],
            sender_deposit,
            retryable_data["to"],
            retryable_data["l2CallValue"],
            retryable_data["excessFeeRefundAddress"],
            retryable_data["callValueRefundAddress"],
            retryable_data["data"],
        ).estimate_gas()

    async def estimate_max_fee_per_gas(self, options=None) -> int:
        """
        Provides an estimate for the child chain maxFeePerGas, adding a margin for volatility.
        """
        defaults = self.apply_max_fee_per_gas_defaults(options)
        base = defaults.get("base")
        if base is None:
            base = self.child_provider.eth.gas_price  # current child chain gas price

        return self.percent_increase(base, defaults["percentIncrease"])

    @staticmethod
    async def is_valid(estimates: dict, re_estimates: dict) -> bool:
        """
        Validate that `estimates` remain safe if compared to fresh `re_estimates` from chain.
        We want to ensure maxFeePerGas & maxSubmissionCost are not underestimates.
        """
        return (
            estimates["maxFeePerGas"] >= re_estimates["maxFeePerGas"]
            and estimates["maxSubmissionCost"] >= re_estimates["maxSubmissionCost"]
        )

    async def estimate_all(
        self,
        retryable_estimate_data: dict,
        parent_base_fee: int,
        parent_provider,
        options=None
    ) -> dict:
        """
        Get gas limit, gas price, submission cost, and deposit needed for a Parent->Child message.
        Merges logic from the updated TS code.
        """
        if options is None:
            options = {}

        data = retryable_estimate_data["data"]

        # Apply defaults
        gas_limit_defaults = self.apply_gas_limit_defaults(options.get("gasLimit", {}))
        max_fee_per_gas_estimate = await self.estimate_max_fee_per_gas(options.get("maxFeePerGas", {}))
        max_submission_fee_estimate = await self.estimate_submission_fee(
            parent_provider,
            parent_base_fee,
            len(data),
            options.get("maxSubmissionFee", {}),
        )

        # Estimate gas limit
        base = gas_limit_defaults.get("base")
        if base is None:
            base = await self.estimate_retryable_ticket_gas_limit(
                retryable_estimate_data, options.get("deposit", {}).get("base")
            )

        calculated_gas_limit = self.percent_increase(base, gas_limit_defaults["percentIncrease"])
        gas_limit = max(calculated_gas_limit, gas_limit_defaults["min"])

        # Now figure out the deposit
        # The new code scales from 18 decimals to the child chain's native decimals if needed
        child_network = get_arbitrum_network(self.child_provider)
        decimals = await get_native_token_decimals({
            "parentProvider": parent_provider,
            "childNetwork": child_network,
        })

        deposit = options.get("deposit", {}).get("base")
        if deposit is None:
            # deposit = gasLimit * maxFeePerGas + maxSubmissionCost + l2CallValue
            # Possibly scaling from 18 decimals to chain-native decimals if they're different.
            deposit_wei = gas_limit * max_fee_per_gas_estimate
            deposit_wei += max_submission_fee_estimate
            deposit_wei += retryable_estimate_data["l2CallValue"]

            deposit = scale_from_18_decimals_to_native_token_decimals({
                "amount": deposit_wei,
                "decimals": decimals,
            })

        return {
            "gasLimit": gas_limit,
            "maxFeePerGas": max_fee_per_gas_estimate,
            "maxSubmissionCost": max_submission_fee_estimate,
            "deposit": deposit,
        }

    async def populate_function_params(self, data_func, parent_provider, gas_overrides=None):
        """
        Transactions that send a Parent->Child message use a two-call approach:
        1) Call with a "dummy" set of gas params to trigger an error containing the real RetryableData.
        2) Parse that error to get the actual data needed for the final call.

        :param data_func: A function that takes partial gas params and returns a transaction request
          dict with shape { "to", "from", "value", "data" }.
        :param parent_provider: The web3 provider for the parent chain
        :param gas_overrides: Dict of overrides for gas limit, fee, submission cost, deposit
        :return: {
            "estimates": ParentToChildMessageGasParams,
            "retryable": dict,
            "data": bytes,
            "to": str,
            "value": int
        }
        """
        if gas_overrides is None:
            gas_overrides = {}

        # These special dummy values will cause the contract to revert with the real RetryableData
        # See RetryableDataTools.ErrorTriggeringParams
        dummy_params = CaseDict({
            "gasLimit": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
            "maxFeePerGas": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
            "maxSubmissionCost": 1,
        })

        null_data_request = data_func(dummy_params)
        retryable = None

        try:
            # We expect a revert with custom data that encodes the RetryableData
            res = parent_provider.eth.call(null_data_request)
            retryable = RetryableDataTools.try_parse_error(res)
            if not is_defined(retryable):
                raise ArbSdkError(f"No retryable data found in error: {res}")

        except Exception as err:
            # Fallback if call(...) raises an exception object that might hold revert data
            # Ethers doesn't natively parse custom revert strings, so we attempt ourselves
            if hasattr(err, "data"):
                retryable = RetryableDataTools.try_parse_error(err.data)

            if not is_defined(retryable):
                raise ArbSdkError(f"No retryable data found in error: {err}")

        # Now use that RetryableData to get real gas estimates
        parent_base_fee = await get_base_fee(parent_provider)
        estimates = await self.estimate_all(
            {
                "from": retryable["from"],
                "to": retryable["to"],
                "data": retryable["data"],
                "l2CallValue": retryable["l2CallValue"],
                "excessFeeRefundAddress": retryable["excessFeeRefundAddress"],
                "callValueRefundAddress": retryable["callValueRefundAddress"],
            },
            parent_base_fee,
            parent_provider,
            gas_overrides,
        )

        # Finally, re-call data_func with the real gas parameters
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
