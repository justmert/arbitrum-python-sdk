import pytest
from eth_account import Account
from web3 import Web3
from web3.eth.eth import TransactionNotFound

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.constants import (
    ARB_RETRYABLE_TX_ADDRESS,
    NODE_INTERFACE_ADDRESS,
)
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.utils.helper import deploy_abi_contract, load_contract
from arbitrum_py.utils.lib import is_defined
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    approve_parent_custom_fee_token_for_erc20_deposit,
    get_parent_custom_fee_token_allowance,
    is_arbitrum_network_with_custom_fee_token,
)
from tests.integration.custom_fee_token.mocha_extensions import (
    it_only_when_custom_gas_token,
)
from tests.integration.test_helpers import (
    GatewayType,
    deposit_token,
    fund_child_signer,
    fund_parent_signer,
    withdraw_token,
)

DEPOSIT_AMOUNT = 100
WITHDRAWAL_AMOUNT = 10


@pytest.fixture(scope="module")
def setup_state():
    setup = setup_testing_env()

    fund_parent_signer(setup["parentSigner"])
    fund_child_signer(setup["childSigner"])

    parent_token = deploy_abi_contract(
        provider=setup["parentSigner"].provider,
        deployer=setup["parentSigner"].account,
        contract_name="TestERC20",
    )
    tx = parent_token.functions.mint().build_transaction({"from": setup["parentSigner"].account.address})
    tx_hash = setup["parentSigner"].provider.eth.send_transaction(tx)
    setup["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    setup["parentToken"] = parent_token
    return setup


@pytest.fixture(scope="function", autouse=True)
def skip_if_mainnet(request, setup_state):
    chain_id = setup_state["childChain"].chain_id
    if chain_id in [42161, 42170]:  # Arbitrum One or Nova
        pytest.skip("Skipping test on mainnet")


def redeem_and_test(setup_state, message, expected_status, gas_limit=None):
    """Helper function to test redemption process"""
    manual_redeem = message.redeem(overrides={"gasLimit": gas_limit})
    retry_rec = manual_redeem.wait_for_redeem()
    redeem_rec = manual_redeem.wait()
    block_hash = redeem_rec.blockHash

    assert retry_rec.blockHash == block_hash, "redeemed in same block"
    assert retry_rec.to == setup_state["childChain"]["tokenBridge"]["childErc20Gateway"], "redeemed in wrong gateway"
    assert retry_rec.status == expected_status, "tx status incorrect"

    message_status = message.status()
    expected_message_status = (
        ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD
        if expected_status == 0
        else ParentToChildMessageStatus.REDEEMED
    )
    assert message_status == expected_message_status, "incorrect message status"


@it_only_when_custom_gas_token
def test_approves_custom_gas_token_to_be_spent_by_relevant_gateway(setup_state):
    parent_signer = setup_state["parentSigner"]
    erc20_bridger = setup_state["erc20Bridger"]

    gateway_address = erc20_bridger.get_parent_gateway_address(
        setup_state["parentToken"].address, parent_signer.provider
    )

    initial_allowance = get_parent_custom_fee_token_allowance(parent_signer.account.address, gateway_address)
    assert initial_allowance == 0, "Initial allowance is not empty"

    tx = erc20_bridger.approve_gas_token(
        {
            "parentSigner": parent_signer,
            "erc20ParentAddress": setup_state["parentToken"].address,
        }
    )
    parent_signer.provider.eth.wait_for_transaction_receipt(tx)

    final_allowance = get_parent_custom_fee_token_allowance(parent_signer.account.address, gateway_address)
    assert final_allowance == 2**256 - 1, "Final allowance is not max uint256"


def test_deposits_erc20(setup_state):
    if is_arbitrum_network_with_custom_fee_token():
        approve_parent_custom_fee_token_for_erc20_deposit(
            setup_state["parentSigner"], setup_state["parentToken"].address
        )

    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.STANDARD,
        }
    )


def test_deposit_with_no_funds_manual_redeem(setup_state):
    result = deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD,
            "expectedGatewayType": GatewayType.STANDARD,
            "retryableOverrides": {"gasLimit": {"base": 0}, "maxFeePerGas": {"base": 0}},
        }
    )

    redeem_and_test(setup_state, message=result["waitRes"]["message"], expected_status=1)


def test_deposit_with_low_funds_manual_redeem(setup_state):
    result = deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD,
            "expectedGatewayType": GatewayType.STANDARD,
            "retryableOverrides": {"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
        }
    )

    redeem_and_test(setup_state, message=result["waitRes"]["message"], expected_status=1)


def test_deposit_with_only_low_gas_limit_manual_redeem_succeeds(setup_state):
    result = deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD,
            "expectedGatewayType": GatewayType.STANDARD,
            "retryableOverrides": {"gasLimit": {"base": 21000}},
        }
    )

    retryable_creation = result["waitRes"]["message"].get_retryable_creation_receipt()
    if not is_defined(retryable_creation):
        raise ArbSdkError("Missing retryable creation.")

    l2_receipt = ChildTransactionReceipt(retryable_creation)
    redeems_scheduled = l2_receipt.get_redeem_scheduled_events()
    assert len(redeems_scheduled) == 1, "Unexpected redeem length"

    with pytest.raises(TransactionNotFound):
        setup_state["childSigner"].provider.eth.get_transaction_receipt(redeems_scheduled[0]["retryTxHash"])

    redeem_and_test(setup_state, message=result["waitRes"]["message"], expected_status=1)


def test_deposit_with_low_funds_fails_first_redeem_succeeds_second(setup_state):
    result = deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD,
            "expectedGatewayType": GatewayType.STANDARD,
            "retryableOverrides": {"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
        }
    )

    arb_retryable_tx = load_contract(
        provider=setup_state["childSigner"].provider,
        contract_name="ArbRetryableTx",
        address=ARB_RETRYABLE_TX_ADDRESS,
    )

    n_interface = load_contract(
        provider=setup_state["childSigner"].provider,
        contract_name="NodeInterface",
        address=NODE_INTERFACE_ADDRESS,
    )

    gas_components = n_interface.functions.gasEstimateComponents(
        arb_retryable_tx.address,
        False,
        arb_retryable_tx.encode_abi(fn_name="redeem", args=[result["waitRes"]["message"].retryable_creation_id]),
    ).call()

    # First redeem attempt - should fail

    redeem_and_test(
        setup_state,
        message=result["waitRes"]["message"],
        expected_status=0,
        gas_limit=gas_components[0] - 15000,
    )

    # Second redeem attempt - should succeed
    redeem_and_test(setup_state, message=result["waitRes"]["message"], expected_status=1)


def test_withdraws_erc20(setup_state):
    child_token_addr = setup_state["erc20Bridger"].get_child_erc20_address(
        setup_state["parentToken"].address, setup_state["parentSigner"].provider
    )

    child_token = setup_state["erc20Bridger"].get_child_token_contract(
        setup_state["childSigner"].provider, child_token_addr
    )

    # 5 deposits above - increase this number if more deposit tests added
    start_balance = DEPOSIT_AMOUNT * 5
    child_balance_start = child_token.functions.balanceOf(setup_state["childSigner"].account.address).call()

    assert str(child_balance_start) == str(child_balance_start)

    withdraw_token(
        {
            **setup_state,
            "amount": WITHDRAWAL_AMOUNT,
            "gatewayType": GatewayType.STANDARD,
            "startBalance": start_balance,
            "parentToken": load_contract(
                provider=setup_state["parentSigner"].provider,
                contract_name="ERC20",
                address=setup_state["parentToken"].address,
            ),
        }
    )


def test_deposits_erc20_with_extra_eth(setup_state):
    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "ethDepositAmount": Web3.to_wei(0.0005, "ether"),
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.STANDARD,
        }
    )


def test_deposits_erc20_with_extra_eth_to_specific_child_address(setup_state):
    random_address = Account.create().address
    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "ethDepositAmount": Web3.to_wei(0.0005, "ether"),
            "parentTokenAddress": setup_state["parentToken"].address,
            "erc20Bridger": setup_state["erc20Bridger"],
            "parentSigner": setup_state["parentSigner"],
            "childSigner": setup_state["childSigner"],
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.STANDARD,
            "destinationAddress": random_address,
        }
    )
