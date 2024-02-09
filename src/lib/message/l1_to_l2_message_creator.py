from src.lib.data_entities.errors import MissingProviderArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.data_entities.transaction_request import is_l1_to_l2_transaction_request
from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.utils.helper import load_contract
from src.lib.utils.lib import get_base_fee


class L1ToL2MessageCreator:
    def __init__(self, l1_signer):
        self.l1_signer = l1_signer
        if not SignerProviderUtils.signer_has_provider(l1_signer):
            raise MissingProviderArbSdkError("l1Signer")

    @staticmethod
    async def get_ticket_estimate(params, l1_provider, l2_provider, retryable_gas_overrides=None):
        base_fee = await get_base_fee(l1_provider)

        gas_estimator = L1ToL2MessageGasEstimator(l2_provider)
        return await gas_estimator.estimate_all(params, base_fee, l1_provider, retryable_gas_overrides)

    @staticmethod
    async def get_ticket_creation_request(params, l1_provider, l2_provider, options=None):
        excess_fee_refund_address = params.get("excessFeeRefundAddress", None)
        if excess_fee_refund_address is None:
            excess_fee_refund_address = params.get("from")

        call_value_refund_address = params.get("callValueRefundAddress", None)
        if call_value_refund_address is None:
            call_value_refund_address = params.get("from")

        parsed_params = {
            **params,
            "excessFeeRefundAddress": excess_fee_refund_address,
            "callValueRefundAddress": call_value_refund_address,
        }

        estimates = await L1ToL2MessageCreator.get_ticket_estimate(parsed_params, l1_provider, l2_provider, options)

        l2_network = get_l2_network(l2_provider)
        inbox_contract = load_contract(
            contract_name="Inbox",
            address=l2_network.eth_bridge.inbox,
            provider=l1_provider,
            is_classic=False,
        )

        function_data = inbox_contract.encodeABI(
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

        tx_request = {
            "to": l2_network.eth_bridge.inbox,
            "data": function_data,
            "value": estimates["deposit"],
            "from": params["from"],
        }

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

        async def is_valid():
            re_estimates = await L1ToL2MessageCreator.get_ticket_estimate(
                parsed_params, l1_provider, l2_provider, options
            )
            return L1ToL2MessageGasEstimator.is_valid(estimates, re_estimates)

        return {
            "txRequest": tx_request,
            "retryableData": retryable_data,
            "isValid": is_valid,
        }

    async def create_retryable_ticket(self, params, l2_provider, options=None):
        l1_provider = SignerProviderUtils.get_provider_or_throw(self.l1_signer)

        if is_l1_to_l2_transaction_request(params):
            create_request = params
        else:
            create_request = await L1ToL2MessageCreator.get_ticket_creation_request(
                params, l1_provider, l2_provider, options
            )

        tx = {**create_request["txRequest"], **params.get("overrides", {})}

        if "from" not in tx:
            tx["from"] = self.l1_signer.account.address

        tx_hash = self.l1_signer.provider.eth.send_transaction(tx)

        tx_receipt = self.l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        return L1TransactionReceipt.monkey_patch_wait(tx_receipt)
