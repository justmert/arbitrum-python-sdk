from web3 import Web3
from web3.contract import Contract
from typing import Any, Dict, Union, Optional
import json
from src.lib.data_entities.networks import get_l2_network
from src.lib.utils.lib import get_base_fee
from src.lib.data_entities.errors import MissingProviderArbSdkError
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.message.l1_to_l2_message_gas_estimator import L1ToL2MessageGasEstimator
from src.lib.utils.helper import load_contract
# Assuming that other necessary classes and functions are implemented in Python


class L1ToL2MessageCreator:
    def __init__(self, l1_signer):
        self.l1_signer = l1_signer
        if not l1_signer.provider:
            raise MissingProviderArbSdkError("l1Signer")

    @staticmethod
    async def get_ticket_estimate(
        params, l1_provider, l2_provider, retryable_gas_overrides=None
    ):
        base_fee = await get_base_fee(l1_provider)

        gas_estimator = L1ToL2MessageGasEstimator(l2_provider)
        return await gas_estimator.estimate_all(
            params, base_fee, l1_provider, retryable_gas_overrides
        )

    @staticmethod
    async def get_ticket_creation_request(
        params, l1_provider, l2_provider, options=None
    ):
        excess_fee_refund_address = params.get(
            "excess_fee_refund_address"
        ) or params.get("from")
        call_value_refund_address = params.get(
            "call_value_refund_address"
        ) or params.get("from")

        parsed_params = {
            **params,
            "excess_fee_refund_address": excess_fee_refund_address,
            "call_value_refund_address": call_value_refund_address,
        }

        estimates = await L1ToL2MessageCreator.get_ticket_estimate(
            parsed_params, l1_provider, l2_provider, options
        )

        l2_network = get_l2_network(l2_provider)
        inbox_contract = load_contract(
            "Inbox", l2_network.eth_bridge.inbox, l1_provider, is_classic=False
        )

        function_data = inbox_contract.encodeABI(
            fn_name="createRetryableTicket",
            args=[
                params["to"],
                params["l2_call_value"],
                estimates["max_submission_cost"],
                excess_fee_refund_address,
                call_value_refund_address,
                estimates["gas_limit"],
                estimates["max_fee_per_gas"],
                params["data"],
            ],
        )

        tx_request = {
            "to": l2_network.eth_bridge.inbox,
            "data": function_data,
            "value": estimates["deposit"],
            "from": params["from"],
        }

        retryable_data = {**params, **estimates}

        async def is_valid():
            re_estimates = await L1ToL2MessageCreator.get_ticket_estimate(
                parsed_params, l1_provider, l2_provider, options
            )
            return all(
                estimates[key] >= re_estimates[key]
                for key in ["max_fee_per_gas", "max_submission_cost"]
            )

        return {
            "tx_request": tx_request,
            "retryable_data": retryable_data,
            "is_valid": is_valid,
        }

    async def create_retryable_ticket(self, params, l2_provider, options=None):
        if "overrides" in params:
            overrides = params["overrides"]
            params.pop("overrides", None)
        else:
            overrides = {}

        l1_provider = self.l1_signer.provider
        create_request = await L1ToL2MessageCreator.get_ticket_creation_request(
            params, l1_provider, l2_provider, options
        )

        tx = await self.l1_signer.send_transaction(
            {**create_request["tx_request"], **overrides}
        )

        # The monkeyPatchWait function needs to be implemented
        return L1TransactionReceipt.monkey_patch_wait(tx)
