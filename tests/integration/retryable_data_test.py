import os

import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError

from src.lib.data_entities.retryable_data import RetryableDataTools
from src.lib.utils.helper import deploy_abi_contract, load_contract
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import (
    fund_l1,
)

DEPOSIT_AMOUNT = Web3.to_wei(100, "wei")


def create_revert_params():
    l2_call_value = 137
    max_submission_cost = 1618
    return {
        "to": Account.create().address,
        "excessFeeRefundAddress": Account.create().address,
        "callValueRefundAddress": Account.create().address,
        "l2CallValue": l2_call_value,
        "data": Web3.to_hex(os.urandom(32)),
        "maxSubmissionCost": max_submission_cost,
        "value": l2_call_value
        + max_submission_cost
        + RetryableDataTools.ErrorTriggeringParams["gasLimit"]
        + RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
        "gasLimit": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
        "maxFeePerGas": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
    }


async def retryable_data_parsing(func_name):
    setup_state = await test_setup()
    l1_signer = setup_state.l1_signer
    l2_network = setup_state.l2_network

    fund_l1(l1_signer)

    inbox_contract = load_contract(
        address=l2_network.eth_bridge.inbox,
        contract_name="Inbox",
        provider=l1_signer.provider,
    )
    revert_params = create_revert_params()

    try:
        if func_name == "estimateGas":
            inbox_contract.functions.createRetryableTicket(
                revert_params["to"],
                revert_params["l2CallValue"],
                revert_params["maxSubmissionCost"],
                revert_params["excessFeeRefundAddress"],
                revert_params["callValueRefundAddress"],
                revert_params["gasLimit"],
                revert_params["maxFeePerGas"],
                revert_params["data"],
            ).estimate_gas({"from": l1_signer.account.address, "value": revert_params["value"]})

        elif func_name == "callStatic":
            inbox_contract.functions.createRetryableTicket(
                revert_params["to"],
                revert_params["l2CallValue"],
                revert_params["maxSubmissionCost"],
                revert_params["excessFeeRefundAddress"],
                revert_params["callValueRefundAddress"],
                revert_params["gasLimit"],
                revert_params["maxFeePerGas"],
                revert_params["data"],
            ).call({"from": l1_signer.account.address, "value": revert_params["value"]})

        assert False, f"Expected {func_name} to fail"

    except ContractCustomError as e:
        parsed_data = RetryableDataTools.try_parse_error(str(e))

        assert parsed_data is not None, "Failed to parse error data"
        assert parsed_data.call_value_refund_address == revert_params["callValueRefundAddress"]

        assert parsed_data.data == Web3.to_bytes(hexstr=revert_params["data"])

        assert str(parsed_data.deposit) == str(revert_params["value"])

        assert parsed_data.excess_fee_refund_address == revert_params["excessFeeRefundAddress"]

        assert parsed_data["from"] == l1_signer.account.address

        assert str(parsed_data.gas_limit) == str(revert_params["gasLimit"])

        assert str(parsed_data.l2_call_value) == str(revert_params["l2CallValue"])

        assert str(parsed_data.max_fee_per_gas) == str(revert_params["maxFeePerGas"])

        assert str(parsed_data.max_submission_cost) == str(revert_params["maxSubmissionCost"])

        assert parsed_data.to == revert_params["to"]


@pytest.mark.asyncio
async def test_does_parse_error_in_estimate_gas():
    await retryable_data_parsing("estimateGas")


@pytest.mark.asyncio
async def test_does_parse_from_call_static():
    await retryable_data_parsing("callStatic")


@pytest.mark.asyncio
async def test_erc20_deposit_comparison():
    setup_state = await test_setup()
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    erc20_bridger = setup_state.erc20_bridger

    fund_l1(l1_signer, Web3.to_wei(2, "ether"))

    test_token = deploy_abi_contract(
        provider=l1_signer.provider, deployer=l1_signer.account, contract_name="TestERC20", is_classic=True
    )

    tx_hash = test_token.functions.mint().transact({"from": l1_signer.account.address})

    l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    l1_token_address = test_token.address

    await erc20_bridger.approve_token({"erc20L1Address": l1_token_address, "l1Signer": l1_signer})

    retryable_overrides = {
        "maxFeePerGas": {
            "base": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
            "percentIncrease": 0,
        },
        "gasLimit": {
            "base": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
            "min": 0,
            "percentIncrease": 0,
        },
    }

    erc20_params = {
        "l1Signer": l1_signer,
        "l2SignerOrProvider": l2_signer.provider,
        "from": l1_signer.account.address,
        "erc20L1Address": l1_token_address,
        "amount": DEPOSIT_AMOUNT,
        "retryableGasOverrides": retryable_overrides,
    }

    deposit_params = await erc20_bridger.get_deposit_request(
        {
            **erc20_params,
            "l1Provider": l1_signer.provider,
            "l2Provider": l2_signer.provider,
        }
    )

    try:
        await erc20_bridger.deposit(
            {
                **erc20_params,
                "l1Signer": l1_signer,
                "l2Provider": l2_signer.provider,
            }
        )
        assert False, "Expected estimateGas to fail"

    except ContractCustomError as e:
        parsed_data = RetryableDataTools.try_parse_error(str(e))

        assert parsed_data is not None, "Failed to parse error"

        assert parsed_data.call_value_refund_address == deposit_params.retryable_data.call_value_refund_address

        assert parsed_data.data == deposit_params.retryable_data.data

        assert str(parsed_data.deposit) == str(deposit_params.tx_request["value"])

        assert parsed_data.excess_fee_refund_address == deposit_params.retryable_data.excess_fee_refund_address

        assert parsed_data["from"] == deposit_params.retryable_data["from"]

        assert str(parsed_data.gas_limit) == str(deposit_params.retryable_data.gas_limit)

        assert str(parsed_data.l2_call_value) == str(deposit_params.retryable_data.l2_call_value)

        assert str(parsed_data.max_fee_per_gas) == str(deposit_params.retryable_data.max_fee_per_gas)

        assert str(parsed_data.max_submission_cost) == str(deposit_params.retryable_data.max_submission_cost)

        assert parsed_data.to == deposit_params.retryable_data.to
