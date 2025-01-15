from typing import Any, Dict, Optional, TypedDict

from web3 import Web3
from web3.types import Wei

from arbitrum_py.data_entities.constants import NODE_INTERFACE_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.data_entities.retryable_data import RetryableDataTools
from arbitrum_py.utils.helper import CaseDict, load_contract, to_checksum_address
from arbitrum_py.utils.lib import (
    get_base_fee,
    get_native_token_decimals,
    is_defined,
    scale_from_18_decimals_to_native_token_decimals,
)

# Constants for gas estimation
DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE = 300
DEFAULT_GAS_PRICE_PERCENT_INCREASE = 500


class PercentIncrease(TypedDict, total=False):
    """
    Configuration for percentage-based increases in gas parameters.

    Attributes:
        base: If provided, will override the estimated base value
        percentIncrease: How much to increase the base by (in percentage)
    """

    base: Optional[Wei]
    percentIncrease: Optional[int]


class GasLimitOverride(PercentIncrease):
    """
    Extended configuration for gas limit estimation.

    Attributes:
        base: If provided, will override the estimated base gas limit
        percentIncrease: How much to increase the base by (in percentage)
        min: Minimum gas limit to enforce
    """

    min: Optional[Wei]


class GasOverrides(TypedDict, total=False):
    """
    Configuration for overriding gas estimation parameters.

    Attributes:
        gasLimit: Override settings for gas limit estimation
        maxSubmissionFee: Override settings for max submission fee
        maxFeePerGas: Override settings for max fee per gas
        deposit: Override settings for deposit amount
    """

    gasLimit: Optional[GasLimitOverride]
    maxSubmissionFee: Optional[PercentIncrease]
    maxFeePerGas: Optional[PercentIncrease]
    deposit: Optional[Dict[str, Wei]]


default_parent_to_child_message_estimate_options = {
    "maxSubmissionFeePercentIncrease": DEFAULT_SUBMISSION_FEE_PERCENT_INCREASE,
    "gasLimitPercentIncrease": 0,
    "maxFeePerGasPercentIncrease": DEFAULT_GAS_PRICE_PERCENT_INCREASE,
}


class ParentToChildMessageGasEstimator:
    """
    Gas estimator for parent-to-child messages in Arbitrum.

    This class provides functionality to estimate gas parameters for sending
    retryable transactions from the parent chain to the child chain. It handles:

    - Gas limit estimation
    - Max fee per gas estimation
    - Submission cost estimation
    - Deposit amount calculation

    The estimator includes safety margins to account for price fluctuations and
    ensures transactions have sufficient gas for execution.
    """

    def __init__(self, child_provider: Web3) -> None:
        """
        Initialize the gas estimator.

        Args:
            child_provider: Web3 provider connected to the child chain
        """
        self.child_provider = child_provider

    def percent_increase(self, num: Wei, increase: int) -> Wei:
        """
        Increase a number by a percentage.

        Args:
            num: Base number to increase
            increase: Percentage to increase by

        Returns:
            Original number increased by the specified percentage
        """
        return num + (num * increase // 100)

    def apply_submission_price_defaults(
        self, max_submission_fee_options: Optional[PercentIncrease] = None
    ) -> PercentIncrease:
        """
        Apply default values for submission price parameters.

        Args:
            max_submission_fee_options: Optional overrides for submission fee calculation

        Returns:
            Dictionary with base and percentIncrease values, using defaults where not specified
        """
        base = max_submission_fee_options.get("base") if max_submission_fee_options else None
        percent_increase = (
            max_submission_fee_options["percentIncrease"]
            if max_submission_fee_options and "percentIncrease" in max_submission_fee_options
            else default_parent_to_child_message_estimate_options["maxSubmissionFeePercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_max_fee_per_gas_defaults(
        self, max_fee_per_gas_options: Optional[PercentIncrease] = None
    ) -> PercentIncrease:
        """
        Apply default values for max fee per gas parameters.

        Args:
            max_fee_per_gas_options: Optional overrides for max fee per gas calculation

        Returns:
            Dictionary with base and percentIncrease values, using defaults where not specified
        """
        base = max_fee_per_gas_options.get("base") if max_fee_per_gas_options else None
        percent_increase = (
            max_fee_per_gas_options["percentIncrease"]
            if max_fee_per_gas_options and "percentIncrease" in max_fee_per_gas_options
            else default_parent_to_child_message_estimate_options["maxFeePerGasPercentIncrease"]
        )
        return {"base": base, "percentIncrease": percent_increase}

    def apply_gas_limit_defaults(self, gas_limit_defaults: Optional[GasLimitOverride] = None) -> GasLimitOverride:
        """
        Apply default values for gas limit parameters.

        Args:
            gas_limit_defaults: Optional overrides for gas limit calculation

        Returns:
            Dictionary with base, percentIncrease, and min values, using defaults where not specified
        """
        base = gas_limit_defaults.get("base") if gas_limit_defaults else None
        percent_increase = (
            gas_limit_defaults["percentIncrease"]
            if gas_limit_defaults and "percentIncrease" in gas_limit_defaults
            else default_parent_to_child_message_estimate_options["gasLimitPercentIncrease"]
        )
        min_gas_limit = gas_limit_defaults["min"] if gas_limit_defaults and "min" in gas_limit_defaults else Wei(0)
        return {"base": base, "percentIncrease": percent_increase, "min": min_gas_limit}

    def estimate_submission_fee(
        self,
        parent_provider: Web3,
        parent_base_fee: Wei,
        call_data_size: int,
        options: Optional[PercentIncrease] = None,
    ) -> Wei:
        """
        Estimate the submission fee for a retryable ticket.

        This method calculates the fee required to submit a new retryable transaction
        with the given call data size. The fee is used to cover the cost of storing
        the retryable ticket on the child chain.

        Args:
            parent_provider: Web3 provider for the parent chain
            parent_base_fee: Current base fee on the parent chain
            call_data_size: Size of the call data in bytes
            options: Optional overrides for fee calculation

        Returns:
            Estimated submission fee in wei

        Example:
            >>> estimator = ParentToChildMessageGasEstimator(child_provider)
            >>> fee = estimator.estimate_submission_fee(
            ...     parent_provider,
            ...     Wei(1000000000),  # 1 gwei
            ...     100,  # 100 bytes of call data
            ... )
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

        return Wei(self.percent_increase(base, defaulted_options["percentIncrease"]))

    def estimate_retryable_ticket_gas_limit(
        self, retryable_data: Dict[str, Any], sender_deposit: Optional[Wei] = None
    ) -> Wei:
        """
        Estimate the gas limit required for a retryable ticket.

        This method estimates the amount of gas needed on the child chain to create
        and execute a retryable transaction. It accounts for both the gas needed to
        create the ticket and the gas needed for the actual execution.

        Args:
            retryable_data: Dictionary containing the retryable transaction parameters
            sender_deposit: Optional deposit amount from the sender

        Returns:
            Estimated gas limit in wei

        Raises:
            ArbSdkError: If the gas estimation fails
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
            to_checksum_address(retryable_data["from"]),
            sender_deposit,
            to_checksum_address(retryable_data["to"]),
            retryable_data["l2CallValue"],
            to_checksum_address(retryable_data["excessFeeRefundAddress"]),
            to_checksum_address(retryable_data["callValueRefundAddress"]),
            retryable_data["data"],
        ).estimate_gas()

    def estimate_max_fee_per_gas(self, options: Optional[PercentIncrease] = None) -> Wei:
        """
        Estimate the max fee per gas for a retryable ticket.

        This method calculates the maximum fee per gas that can be paid for a
        retryable transaction. It includes a safety margin to account for price
        fluctuations.

        Args:
            options: Optional overrides for max fee per gas calculation

        Returns:
            Estimated max fee per gas in wei
        """
        defaults = self.apply_max_fee_per_gas_defaults(options)
        base = defaults.get("base")
        if base is None:
            base = self.child_provider.eth.gas_price  # current child chain gas price

        return Wei(self.percent_increase(base, defaults["percentIncrease"]))

    @staticmethod
    def is_valid(estimates: Dict[str, Wei], re_estimates: Dict[str, Wei]) -> bool:
        """
        Validate that the estimates remain safe if compared to fresh re-estimates from chain.

        Args:
            estimates: Original estimates
            re_estimates: Re-estimated values

        Returns:
            True if the original estimates are still safe, False otherwise
        """
        return (
            estimates["maxFeePerGas"] >= re_estimates["maxFeePerGas"]
            and estimates["maxSubmissionCost"] >= re_estimates["maxSubmissionCost"]
        )

    def estimate_all(
        self,
        retryable_estimate_data: Dict[str, Any],
        parent_base_fee: Wei,
        parent_provider: Web3,
        options: Optional[GasOverrides] = None,
    ) -> Dict[str, Wei]:
        """
        Estimate all gas parameters for a retryable ticket.

        This method estimates the gas limit, max fee per gas, submission cost, and
        deposit amount required for a retryable transaction.

        Args:
            retryable_estimate_data: Dictionary containing the retryable transaction parameters
            parent_base_fee: Current base fee on the parent chain
            parent_provider: Web3 provider for the parent chain
            options: Optional overrides for gas estimation parameters

        Returns:
            Dictionary containing the estimated gas parameters
        """
        if options is None:
            options = {}

        data = retryable_estimate_data["data"]

        # Apply defaults
        gas_limit_defaults = self.apply_gas_limit_defaults(options.get("gasLimit", {}))
        max_fee_per_gas_estimate = self.estimate_max_fee_per_gas(options.get("maxFeePerGas", {}))
        max_submission_fee_estimate = self.estimate_submission_fee(
            parent_provider,
            parent_base_fee,
            len(data),
            options.get("maxSubmissionFee", {}),
        )

        # Estimate gas limit
        base = gas_limit_defaults.get("base")
        if base is None:
            base = self.estimate_retryable_ticket_gas_limit(
                retryable_estimate_data, options.get("deposit", {}).get("base")
            )

        calculated_gas_limit = self.percent_increase(base, gas_limit_defaults["percentIncrease"])
        gas_limit = max(calculated_gas_limit, gas_limit_defaults["min"])

        # Now figure out the deposit
        # The new code scales from 18 decimals to the child chain's native decimals if needed
        child_network = get_arbitrum_network(self.child_provider)
        decimals = get_native_token_decimals(
            parent_provider=parent_provider,
            child_network=child_network,
        )

        deposit = options.get("deposit", {}).get("base")
        if deposit is None:
            # deposit = gasLimit * maxFeePerGas + maxSubmissionCost + l2CallValue
            # Possibly scaling from 18 decimals to chain-native decimals if they're different.
            deposit_wei = gas_limit * max_fee_per_gas_estimate
            deposit_wei += max_submission_fee_estimate
            deposit_wei += retryable_estimate_data["l2CallValue"]

            deposit = scale_from_18_decimals_to_native_token_decimals(
                amount=deposit_wei,
                decimals=decimals,
            )
        return {
            "gasLimit": gas_limit,
            "maxFeePerGas": max_fee_per_gas_estimate,
            "maxSubmissionCost": max_submission_fee_estimate,
            "deposit": deposit,
        }

    def populate_function_params(self, data_func, parent_provider: Web3, gas_overrides: Optional[GasOverrides] = None):
        """
        Populate function parameters for a retryable ticket.

        This method generates the necessary parameters for a retryable transaction,
        including the gas limit, max fee per gas, submission cost, and deposit amount.

        Args:
            data_func: Function that generates the transaction data
            parent_provider: Web3 provider for the parent chain
            gas_overrides: Optional overrides for gas estimation parameters

        Returns:
            Dictionary containing the populated function parameters
        """
        if gas_overrides is None:
            gas_overrides = {}

        # These special dummy values will cause the contract to revert with the real RetryableData
        # See RetryableDataTools.ErrorTriggeringParams
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
        parent_base_fee = get_base_fee(parent_provider)
        estimates = self.estimate_all(
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
