from typing import Any, Callable, Dict, Optional, Union

from web3 import Web3

from arbitrum_py.data_entities.errors import MissingProviderArbSdkError
from arbitrum_py.data_entities.networks import (
    get_arbitrum_network,
    is_arbitrum_network_native_token_ether,
)
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.data_entities.transaction_request import (
    is_parent_to_child_transaction_request,
)
from arbitrum_py.message.parent_to_child_message_gas_estimator import (
    GasOverrides,
    ParentToChildMessageGasEstimator,
)
from arbitrum_py.message.parent_transaction import ParentTransactionReceipt
from arbitrum_py.utils.helper import create_contract_instance
from arbitrum_py.utils.lib import get_base_fee


class ParentToChildMessageCreator:
    """
    Creates retryable tickets by directly calling the Inbox contract on the Parent chain.

    This class handles the creation and management of cross-chain messages from a parent
    chain to a child chain in the Arbitrum ecosystem. It provides functionality to create
    retryable tickets, estimate gas costs, generate transaction requests, and handle both
    ETH and ERC20 token transfers.
    """

    def __init__(self, parent_signer: Any) -> None:
        """
        Initialize the message creator with a parent chain signer.

        Args:
            parent_signer: The parent-chain signer object that must have a provider

        Raises:
            MissingProviderArbSdkError: If the provided signer lacks a provider
        """
        self.parent_signer = parent_signer
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

    @staticmethod
    def get_ticket_estimate(
        params: Dict[str, Any],
        parent_provider: Web3,
        child_provider: Web3,
        retryable_gas_overrides: Optional[GasOverrides] = None,
    ) -> Dict[str, Any]:
        """
        Get current gas estimates for creating a retryable ticket on the child chain.

        This method calculates the gas parameters needed for creating a retryable ticket,
        including maxSubmissionCost, maxFeePerGas, gasLimit, and deposit amounts.

        Args:
            params: Parameters for the retryable ticket
            parent_provider: Web3 provider for the Parent chain
            child_provider: Web3 provider for the Child chain
            retryable_gas_overrides: Optional gas override parameters

        Returns:
            Dictionary containing gas estimation parameters including maxSubmissionCost,
            maxFeePerGas, gasLimit, and deposit
        """
        base_fee = get_base_fee(parent_provider)
        gas_estimator = ParentToChildMessageGasEstimator(child_provider)
        return gas_estimator.estimate_all(params, base_fee, parent_provider, retryable_gas_overrides)

    @staticmethod
    def get_ticket_creation_request_call_data(
        params: Dict[str, Any],
        estimates: Dict[str, Any],
        excess_fee_refund_address: str,
        call_value_refund_address: str,
        native_token_is_eth: bool,
    ) -> bytes:
        """
        Prepare calldata for creating a retryable ticket.

        This method generates the appropriate contract call data based on whether
        the child chain uses ETH or ERC20 tokens natively. It encodes the function
        call parameters according to the contract's ABI.

        Args:
            params: Parameters for the retryable ticket
            estimates: Gas estimates for the transaction
            excess_fee_refund_address: Address to refund excess fees
            call_value_refund_address: Address to refund unused call value
            native_token_is_eth: Whether the child chain uses ETH natively

        Returns:
            Encoded contract call data as bytes
        """
        # We look up the contract factory in the same way the TS code calls
        # Inbox__factory.createInterface() or ERC20Inbox__factory.createInterface()
        if not native_token_is_eth:
            # use ERC20Inbox
            erc20_inbox_contract = create_contract_instance(
                contract_name="ERC20Inbox",
                # address="0x",  # Not used in encodeABI, so dummy
                # provider=None,  # We only need the ABI here
            )
            return erc20_inbox_contract.encodeABI(
                fn_name="createRetryableTicket",
                args=[
                    params["to"],
                    params["l2CallValue"],
                    estimates["maxSubmissionCost"],
                    excess_fee_refund_address,
                    call_value_refund_address,
                    estimates["gasLimit"],
                    estimates["maxFeePerGas"],
                    estimates["deposit"],  # tokenTotalFeeAmount
                    params["data"],
                ],
            )

        # else, native token is ETH -> use Inbox
        inbox_contract = create_contract_instance(
            contract_name="Inbox",
            # address="0x",
            # provider=None,
        )
        return inbox_contract.encodeABI(
            fn_name="createRetryableTicket",
            args=[
                params["to"],
                params["l2CallValue"],
                estimates["maxSubmissionCost"],
                excess_fee_refund_address,
                call_value_refund_address,
                estimates["gasLimit"],
                estimates["maxFeePerGas"],
                params["data"],
            ],
        )

    @staticmethod
    def get_ticket_creation_request(
        params: Dict[str, Any],
        parent_provider: Web3,
        child_provider: Web3,
        options: Optional[GasOverrides] = None,
    ) -> Dict[str, Union[Dict[str, Any], Callable[[], bool]]]:
        """
        Generate a transaction request for creating a retryable ticket.

        This method prepares all necessary parameters and data for creating
        a retryable ticket transaction. It handles the preparation of gas
        estimates, contract call data, and transaction parameters.

        Args:
            params: Parameters for the retryable ticket
            parent_provider: The parent chain provider
            child_provider: The child chain provider
            options: Optional gas override parameters

        Returns:
            Dictionary containing:
                - txRequest: Transaction parameters (to, data, value, from)
                - retryableData: Retryable ticket parameters
                - isValid: Function to validate gas estimates
        """
        if options is None:
            options = {}

        excess_fee_refund_address = params.get("excessFeeRefundAddress") or params.get("from")
        call_value_refund_address = params.get("callValueRefundAddress") or params.get("from")

        # Combine any missing fields with defaults
        parsed_params = {
            **params,
            "excessFeeRefundAddress": excess_fee_refund_address,
            "callValueRefundAddress": call_value_refund_address,
        }

        # Estimate relevant gas values
        estimates = ParentToChildMessageCreator.get_ticket_estimate(
            parsed_params, parent_provider, child_provider, options
        )

        # Identify the child chain
        child_network = get_arbitrum_network(child_provider)
        native_token_is_eth = is_arbitrum_network_native_token_ether(child_network)

        # Prepare the calldata
        function_data = ParentToChildMessageCreator.get_ticket_creation_request_call_data(
            params,
            estimates,
            excess_fee_refund_address,
            call_value_refund_address,
            native_token_is_eth,
        )

        # Final transaction request
        tx_request = {
            "to": child_network.ethBridge.inbox,
            "data": function_data,
            "value": estimates["deposit"] if native_token_is_eth else 0,
            "from": params["from"],
        }

        # Construct the final 'retryableData'
        retryable_data = {
            "data": params["data"],
            "from": params["from"],
            "to": params["to"],
            "excessFeeRefundAddress": excess_fee_refund_address,
            "callValueRefundAddress": call_value_refund_address,
            "l2CallValue": params["l2CallValue"],
            "maxSubmissionCost": estimates["maxSubmissionCost"],
            "maxFeePerGas": estimates["maxFeePerGas"],
            "gasLimit": estimates["gasLimit"],
            "deposit": estimates["deposit"],
        }

        def is_valid():
            re_estimates = ParentToChildMessageCreator.get_ticket_estimate(
                parsed_params, parent_provider, child_provider, options
            )
            return ParentToChildMessageGasEstimator.is_valid(estimates, re_estimates)

        return {
            "txRequest": tx_request,
            "retryableData": retryable_data,
            "isValid": is_valid,
        }

    def create_retryable_ticket(
        self, params: Dict[str, Any], child_provider: Web3, options: Optional[GasOverrides] = None
    ) -> ParentTransactionReceipt:
        """
        Send a transaction on the parent chain to create a retryable ticket.

        This method handles the actual submission of the transaction to create
        a retryable ticket on the parent chain. It processes the transaction
        parameters and waits for the transaction to be confirmed.

        Args:
            params: Either a ParentToChildMessageParams dict or a
                   ParentToChildTransactionRequest
            child_provider: A web3 provider for the child chain
            options: Optional gas override parameters

        Returns:
            Transaction receipt wrapped in a ParentTransactionReceipt object
        """
        parent_provider = SignerProviderUtils.get_provider_or_throw(self.parent_signer)

        # Distinguish if 'params' is already a ParentToChildTransactionRequest or not

        if is_parent_to_child_transaction_request(params):
            create_request = params
        else:
            create_request = ParentToChildMessageCreator.get_ticket_creation_request(
                params, parent_provider, child_provider, options
            )

        # Merge any local overrides into the final tx
        tx = {**create_request["txRequest"], **params.get("overrides", {})}

        # If caller didn't set "from", set it from the signer's account
        if "from" not in tx:
            tx["from"] = self.parent_signer.account.address

        if "gasPrice" not in tx:
            if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
                pass
            else:
                tx["gasPrice"] = parent_provider.eth.gas_price

        if "nonce" not in tx:
            tx["nonce"] = parent_provider.eth.get_transaction_count(self.parent_signer.account.address)

        if "chainId" not in tx:
            tx["chainId"] = parent_provider.eth.chain_id

        if "gas" not in tx:
            tx["gas"] = parent_provider.eth.estimate_gas(tx)

        signed_tx = self.parent_signer.account.sign_transaction(tx)

        # Send the transaction on the parent chain
        tx_hash = parent_provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        # Wait for receipt, then wrap in a ParentTransactionReceipt
        receipt = parent_provider.eth.wait_for_transaction_receipt(tx_hash)
        return ParentTransactionReceipt.monkey_patch_wait(receipt)
