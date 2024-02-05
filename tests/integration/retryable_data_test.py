from re import A
import pytest
from web3 import Web3, HTTPProvider
from web3.contract import Contract
from eth_account import Account
from eth_utils import to_hex
import os
import random
import pytest
from src.lib.utils.helper import deploy_abi_contract, load_contract
from test import CaseDict
from .test_helpers import (
    deploy_test_erc20,
    fund_l1,
    mint_tokens,
)
from src.scripts.test_setup import test_setup
from src.lib.data_entities.retryable_data import RetryableDataTools, RetryableData
import random
from web3.exceptions import ContractCustomError

# Assuming that load_contract is a utility function to load a contract
# from its ABI and address, and that fund_l1 is a utility function to fund an account on L1

DEPOSIT_AMOUNT = Web3.to_wei(100, "wei")


def create_revert_params():
    l2_call_value = Web3.to_wei(137, "wei")
    max_submission_cost = Web3.to_wei(1618, "wei")
    return {
        "to": Account.create().address,
        "excessFeeRefundAddress": Account.create().address,
        "callValueRefundAddress": Account.create().address,
        "l2CallValue": l2_call_value,
        "data": to_hex(os.urandom(32)),
        "maxSubmissionCost": max_submission_cost,
        "value": l2_call_value
        + max_submission_cost
        + RetryableDataTools.ErrorTriggeringParams["gasLimit"]
        + RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
        "gasLimit": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
        "maxFeePerGas": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
    }


async def retryable_data_parsing(func_name):
    # Test setup function
    setup_state = await test_setup()
    l1_signer = setup_state.l1_signer
    l2_network = setup_state.l2_network

    # Fund L1 account
    fund_l1(l1_signer)

    inbox_contract = load_contract(
        address=l2_network.eth_bridge.inbox,
        contract_name="Inbox",
        provider=l1_signer.provider,
    )
    revert_params = create_revert_params()

    try:
        if func_name == "estimateGas":
            _gas_estimate = inbox_contract.functions.createRetryableTicket(
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
        # Use RetryableDataTools to parse the error message
        parsed_data = RetryableDataTools.try_parse_error(str(e))
        # Perform assertions based on the parsed data
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

    # Fund L1 account
    fund_l1(l1_signer, Web3.to_wei(2, "ether"))

    # Deploy ERC20 token and mint tokens
    # erc20_factory = load_contract(contract_name="TestERC20", provider=l1_signer.provider)
    # erc20_factory = deploy_abi_contract(provider=l1_signer.provider, deployer=l1_signer.account, contract_name="TestERC20", is_classic=True)

    # # test_token = erc20_factory.constructor().transact({'from': l1_signer.account.address})

    # await l1_signer.provider.eth.wait_for_transaction_receipt(test_token)
    # test_token_contract = load_contract(address=test_token, contract_name="TestERC20", provider=l1_signer.provider)
    # test_token_contract.functions.mint().transact({'from': l1_signer.account.address})

    test_token = deploy_test_erc20(setup_state.l1_signer.provider, setup_state.l1_signer.account)
    print("deployed_erc20_address", test_token)

    mint_receipt = mint_tokens(
        setup_state.l1_signer.provider,
        test_token.address,
        setup_state.l1_signer.account,
    )
    print("mint_receipt", mint_receipt)

    l1_token_address = test_token.address

    # Approve token on L1
    await erc20_bridger.approve_token(CaseDict({"erc20L1Address": l1_token_address, "l1Signer": l1_signer}))

    # Set up retryable overrides
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

    # Prepare deposit parameters
    erc20_params = CaseDict(
        {
            "l1_signer": l1_signer,
            "l2_signer_or_provider": l2_signer.provider,
            "from": l1_signer.account.address,
            "erc20_l1_address": l1_token_address,
            "amount": DEPOSIT_AMOUNT,
            "retryable_gas_overrides": retryable_overrides,
        }
    )

    deposit_params = await erc20_bridger.get_deposit_request(
        {
            **erc20_params,
            "l1Provider": l1_signer.provider,
            "l2Provider": l2_signer.provider,
        }
    )

    print("my_deposit_params", deposit_params)
    # await erc20_bridger.deposit({
    #     **erc20_params,
    #     "l1Signer": l1_signer,
    #     "l2Provider": l2_signer.provider,
    # })

    # await erc20_bridger.deposit(erc20_params)
    # Attempt to deposit and catch expected failure
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
        # Parse error using RetryableDataTools
        parsed_data = RetryableDataTools.try_parse_error(str(e))
        print("parsed_data", parsed_data)
        assert parsed_data is not None, "Failed to parse error"
        print("deposit_params", deposit_params)
        # Perform assertions
        assert parsed_data.call_value_refund_address == deposit_params.retryable_data.call_value_refund_address
        print("parsed_data.data", parsed_data.data)
        print("deposit_params.retryable_data.data", deposit_params.retryable_data.data)
        assert parsed_data.data == deposit_params.retryable_data.data
        assert str(parsed_data.deposit) == str(deposit_params.tx_request["value"])
        assert parsed_data.excess_fee_refund_address == deposit_params.retryable_data.excess_fee_refund_address
        assert parsed_data["from"] == deposit_params.retryable_data["from"]
        assert str(parsed_data.gas_limit) == str(deposit_params.retryable_data.gas_limit)
        assert str(parsed_data.l2_call_value) == str(deposit_params.retryable_data.l2_call_value)
        assert str(parsed_data.max_fee_per_gas) == str(deposit_params.retryable_data.max_fee_per_gas)
        assert str(parsed_data.max_submission_cost) == str(deposit_params.retryable_data.max_submission_cost)
        assert parsed_data.to == deposit_params.retryable_data.to
