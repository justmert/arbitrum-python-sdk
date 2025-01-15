import os

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.retryable_data import RetryableDataTools
from arbitrum_py.utils.helper import deploy_abi_contract, load_contract
from arbitrum_py.utils.lib import (
    get_native_token_decimals,
    scale_from_18_decimals_to_native_token_decimals,
)
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    is_arbitrum_network_with_custom_fee_token,
)
from tests.integration.test_helpers import fund_parent_signer

DEPOSIT_AMOUNT = Web3.to_wei(100, "wei")


def create_revert_params():
    """Create parameters that will trigger a revert"""
    l2_call_value = 137
    max_submission_cost = 1618

    setup_state = setup_testing_env()
    parent_provider = setup_state.parent_signer.provider
    child_chain = setup_state.child_chain
    decimals = get_native_token_decimals(parent_provider=parent_provider, child_network=child_chain)

    base_value = (
        l2_call_value
        + max_submission_cost
        + RetryableDataTools.ErrorTriggeringParams["gasLimit"]
        + RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"]
    )

    value = scale_from_18_decimals_to_native_token_decimals(amount=base_value, decimals=decimals)

    return {
        "to": Account.create().address,
        "excessFeeRefundAddress": Account.create().address,
        "callValueRefundAddress": Account.create().address,
        "l2CallValue": l2_call_value,
        "data": Web3.to_hex(os.urandom(32)),
        "maxSubmissionCost": max_submission_cost,
        "value": value,
        "gasLimit": RetryableDataTools.ErrorTriggeringParams["gasLimit"],
        "maxFeePerGas": RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"],
    }


def retryable_data_parsing(func_name):
    """Test parsing of retryable data from errors"""
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_chain = setup_state.child_chain

    fund_parent_signer(parent_signer)
    revert_params = create_revert_params()

    try:
        if is_arbitrum_network_with_custom_fee_token():
            inbox_contract = load_contract(
                address=child_chain.eth_bridge.inbox,
                contract_name="ERC20Inbox",
                provider=parent_signer.provider,
            )
            # Custom fee token version
            if func_name == "estimateGas":
                inbox_contract.functions.createRetryableTicket(
                    revert_params["to"],
                    revert_params["l2CallValue"],
                    revert_params["maxSubmissionCost"],
                    revert_params["excessFeeRefundAddress"],
                    revert_params["callValueRefundAddress"],
                    revert_params["gasLimit"],
                    revert_params["maxFeePerGas"],
                    revert_params["value"],
                    revert_params["data"],
                ).estimate_gas({"from": parent_signer.account.address})
            else:
                inbox_contract.functions.createRetryableTicket(
                    revert_params["to"],
                    revert_params["l2CallValue"],
                    revert_params["maxSubmissionCost"],
                    revert_params["excessFeeRefundAddress"],
                    revert_params["callValueRefundAddress"],
                    revert_params["gasLimit"],
                    revert_params["maxFeePerGas"],
                    revert_params["value"],
                    revert_params["data"],
                ).call({"from": parent_signer.account.address})
        else:
            # Standard ETH version
            inbox_contract = load_contract(
                address=child_chain.eth_bridge.inbox,
                contract_name="Inbox",
                provider=parent_signer.provider,
            )
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
                ).estimate_gas({"from": parent_signer.account.address, "value": revert_params["value"]})
            else:
                inbox_contract.functions.createRetryableTicket(
                    revert_params["to"],
                    revert_params["l2CallValue"],
                    revert_params["maxSubmissionCost"],
                    revert_params["excessFeeRefundAddress"],
                    revert_params["callValueRefundAddress"],
                    revert_params["gasLimit"],
                    revert_params["maxFeePerGas"],
                    revert_params["data"],
                ).call({"from": parent_signer.account.address, "value": revert_params["value"]})

        assert False, f"Expected {func_name} to fail"

    except ContractCustomError as e:
        parsed_data = RetryableDataTools.try_parse_error(str(e))
        assert parsed_data is not None, "Failed to parse error data"
        assert parsed_data.call_value_refund_address == revert_params["callValueRefundAddress"]
        assert parsed_data.data == Web3.to_bytes(hexstr=revert_params["data"])
        assert str(parsed_data.deposit) == str(revert_params["value"])
        assert parsed_data.excess_fee_refund_address == revert_params["excessFeeRefundAddress"]
        assert parsed_data["from"] == parent_signer.account.address
        assert str(parsed_data.gas_limit) == str(revert_params["gasLimit"])
        assert str(parsed_data.l2_call_value) == str(revert_params["l2CallValue"])
        assert str(parsed_data.max_fee_per_gas) == str(revert_params["maxFeePerGas"])
        assert str(parsed_data.max_submission_cost) == str(revert_params["maxSubmissionCost"])
        assert parsed_data.to == revert_params["to"]


def test_does_parse_error_in_estimate_gas():
    retryable_data_parsing("estimateGas")


def test_does_parse_from_call_static():
    retryable_data_parsing("callStatic")


def test_erc20_deposit_comparison():
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    erc20_bridger = setup_state.erc20_bridger

    fund_parent_signer(parent_signer, Web3.to_wei(2, "ether"))

    test_token = deploy_abi_contract(
        provider=parent_signer.provider,
        deployer=parent_signer.account,
        contract_name="TestERC20",
    )

    tx = test_token.functions.mint().build_transaction(
        {
            "from": parent_signer.account.address,
            "nonce": parent_signer.provider.eth.get_transaction_count(parent_signer.account.address),
        }
    )
    signed_tx = parent_signer.account.sign_transaction(tx)
    tx_hash = parent_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
    parent_token_address = test_token.address

    # Approve token
    erc20_bridger.approve_token({"erc20ParentAddress": parent_token_address, "parentSigner": parent_signer})

    # Approve custom fee token if needed
    if is_arbitrum_network_with_custom_fee_token():
        erc20_bridger.approve_gas_token(
            {
                "parentSigner": parent_signer,
                "erc20ParentAddress": parent_token_address,
            }
        )

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
        "parentSigner": parent_signer,
        "childSignerOrProvider": child_signer.provider,
        "from": parent_signer.account.address,
        "erc20ParentAddress": parent_token_address,
        "amount": DEPOSIT_AMOUNT,
        "retryableGasOverrides": retryable_overrides,
    }

    deposit_params = erc20_bridger.get_deposit_request(
        {
            **erc20_params,
            "parentProvider": parent_signer.provider,
            "childProvider": child_signer.provider,
        }
    )

    try:
        erc20_bridger.deposit(
            {
                **erc20_params,
                "parentSigner": parent_signer,
                "childProvider": child_signer.provider,
            }
        )
        assert False, "Expected estimateGas to fail"

    except ContractCustomError as e:
        parsed_data = RetryableDataTools.try_parse_error(str(e))
        assert parsed_data is not None, "Failed to parse error"

        assert parsed_data.call_value_refund_address == deposit_params.retryable_data.call_value_refund_address
        assert parsed_data.data == deposit_params.retryable_data.data

        expected_deposit = (
            deposit_params.retryable_data.deposit
            if is_arbitrum_network_with_custom_fee_token()
            else deposit_params.tx_request["value"]
        )
        assert str(parsed_data.deposit) == str(expected_deposit)

        assert parsed_data.excess_fee_refund_address == deposit_params.retryable_data.excess_fee_refund_address
        assert parsed_data["from"] == deposit_params.retryable_data["from"]
        assert str(parsed_data.gas_limit) == str(deposit_params.retryable_data.gas_limit)
        assert str(parsed_data.l2_call_value) == str(deposit_params.retryable_data.l2_call_value)
        assert str(parsed_data.max_fee_per_gas) == str(deposit_params.retryable_data.max_fee_per_gas)
        assert str(parsed_data.max_submission_cost) == str(deposit_params.retryable_data.max_submission_cost)
        assert parsed_data.to == deposit_params.retryable_data.to
