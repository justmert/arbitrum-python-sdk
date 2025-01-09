from src.lib.data_entities.errors import MissingProviderArbSdkError
from src.lib.data_entities.networks import (
    get_arbitrum_network,
    is_arbitrum_network_native_token_ether,
)
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.data_entities.transaction_request import (
    is_parent_to_child_transaction_request,
)
from src.lib.message.parent_to_child_message_gas_estimator import (
    ParentToChildMessageGasEstimator,
)
from src.lib.message.parent_transaction import ParentTransactionReceipt
from src.lib.utils.helper import create_contract_instance
from src.lib.utils.lib import get_base_fee


class ParentToChildMessageCreator:
    """
    Python equivalent of the new ParentToChildMessageCreator (v4).
    Creates retryable tickets by directly calling the Inbox contract on the Parent chain.
    """

    def __init__(self, parent_signer):
        """
        :param parent_signer: The parent-chain signer object that must have a provider
        """
        self.parent_signer = parent_signer
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

    @staticmethod
    def get_ticket_estimate(params: dict, parent_provider, child_provider, retryable_gas_overrides=None) -> dict:
        """
        Gets current gas estimates (maxFeePerGas, maxSubmissionCost, gasLimit, deposit)
        for creating a retryable ticket on the child chain.

        :param params: A dictionary containing ParentToChildMessageNoGasParams fields
        :param parent_provider: Web3 provider for the Parent chain
        :param child_provider: Web3 provider for the Child chain
        :param retryable_gas_overrides: Optional dict of GasOverrides
        :return: A dict with keys "maxSubmissionCost", "maxFeePerGas", "gasLimit", "deposit"
        """
        base_fee = get_base_fee(parent_provider)
        gas_estimator = ParentToChildMessageGasEstimator(child_provider)
        return gas_estimator.estimate_all(params, base_fee, parent_provider, retryable_gas_overrides)

    @staticmethod
    def get_ticket_creation_request_call_data(
        params: dict,
        estimates: dict,
        excess_fee_refund_address: str,
        call_value_refund_address: str,
        native_token_is_eth: bool,
    ) -> bytes:
        """
        Prepare calldata for a call to create a retryable ticket.
        Uses either Inbox or ERC20Inbox logic depending on whether the child chain uses ETH natively.
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
    def get_ticket_creation_request(params: dict, parent_provider, child_provider, options=None) -> dict:
        """
        Generate a transaction request for creating a retryable ticket.

        :param params: A dictionary containing ParentToChildMessageParams fields
        :param parent_provider: The parent chain provider
        :param child_provider: The child chain provider
        :param options: Optional GasOverrides
        :return: A dict with keys:
            {
              "txRequest": { "to", "data", "value", "from" },
              "retryableData": { ... },
              "isValid": fn() -> bool
            }
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
            params, estimates, excess_fee_refund_address, call_value_refund_address, native_token_is_eth
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

    def create_retryable_ticket(self, params: dict, child_provider, options=None):
        """
        Actually sends the transaction on the parent chain to create the retryable ticket.

        :param params: Either a ParentToChildMessageParams dict OR a ParentToChildTransactionRequest
        :param child_provider: A web3 provider for the child chain
        :param options: Optional GasOverrides
        :return: ParentContractTransaction object (with a receipt)
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

        # Send the transaction on the parent chain
        tx_hash = self.parent_signer.provider.eth.send_transaction(tx)

        # Wait for receipt, then wrap in a ParentTransactionReceipt
        receipt = self.parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        return ParentTransactionReceipt.monkey_patch_wait(receipt)
