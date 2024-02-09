import pytest

from src.lib.data_entities.constants import (
    ARB_RETRYABLE_TX_ADDRESS,
    NODE_INTERFACE_ADDRESS,
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.utils.helper import deploy_abi_contract, load_contract
from src.lib.utils.lib import get_transaction_receipt, is_defined
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import (
    GatewayType,
    deposit_token,
    fund_l1,
    fund_l2,
    withdraw_token,
)

DEPOSIT_AMOUNT = 100
WITHDRAWAL_AMOUNT = 10


@pytest.fixture(scope="module")
async def setup_state():
    setup = await test_setup()

    fund_l1(setup.l1_signer)
    fund_l2(setup.l2_signer)

    test_token = deploy_abi_contract(
        provider=setup.l1_signer.provider,
        deployer=setup.l1_signer.account,
        contract_name="TestERC20",
        is_classic=True,
    )
    tx_hash = test_token.functions.mint().transact({"from": setup.l1_signer.account.address})

    setup.l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    setup["l1Token"] = test_token
    return setup


@pytest.fixture(scope="function", autouse=True)
async def skip_if_mainnet(request, setup_state):
    chain_id = setup_state.l1_network.chain_id
    if chain_id == 1:
        pytest.skip("Skipping test on mainnet")


@pytest.mark.asyncio
async def test_deposit_erc20(setup_state):
    await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token.address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.REDEEMED,
        expected_gateway_type=GatewayType.STANDARD,
    )


@pytest.mark.asyncio
async def redeem_and_test(setup_state, message, expected_status, gas_limit=None):
    manual_redeem = await message.redeem(overrides={"gasLimit": gas_limit})
    retry_rec = await manual_redeem.wait_for_redeem()
    redeem_rec = await manual_redeem.wait()
    block_hash = redeem_rec.blockHash
    assert retry_rec.blockHash == block_hash, "redeemed in same block"
    assert retry_rec.to == setup_state["l2Network"]["tokenBridge"]["l2ERC20Gateway"], "redeemed in same block"
    assert retry_rec.status == expected_status, "tx didn't fail"
    assert await message.status() == (
        L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2 if expected_status == 0 else L1ToL2MessageStatus.REDEEMED
    ), "message status"


@pytest.mark.asyncio
async def test_deposit_with_no_funds_manual_redeem(setup_state):
    deposit_token_params = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token.address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 0}, "maxFeePerGas": {"base": 0}},
    )
    wait_res = deposit_token_params["waitRes"]
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_low_funds_manual_redeem(setup_state):
    deposit_token_params = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token.address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
    )
    wait_res = deposit_token_params["waitRes"]
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_only_low_gas_limit_manual_redeem_success(setup_state):
    deposit_token_params = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token.address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 21000}},
    )
    wait_res = deposit_token_params["waitRes"]

    retryable_creation = await wait_res["message"].get_retryable_creation_receipt()
    if not is_defined(retryable_creation):
        raise ArbSdkError("Missing retryable creation.")

    l2_receipt = L2TransactionReceipt(retryable_creation)
    redeems_scheduled = l2_receipt.get_redeem_scheduled_events(provider=setup_state.l2_signer.provider)
    assert len(redeems_scheduled) == 1, "Unexpected redeem length"
    retry_receipt = await get_transaction_receipt(
        tx_hash=redeems_scheduled[0]["retryTxHash"],
        provider=setup_state.l2_signer.provider,
    )
    assert retry_receipt is None, "Retry should not exist"

    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_low_funds_fails_first_redeem_then_succeeds(setup_state):
    deposit_token_params = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token.address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
    )

    wait_res = deposit_token_params["waitRes"]

    arb_retryable_tx = load_contract(
        provider=setup_state.l2_signer.provider,
        contract_name="ArbRetryableTx",
        address=ARB_RETRYABLE_TX_ADDRESS,
        is_classic=False,
    )
    n_interface = load_contract(
        provider=setup_state.l2_signer.provider,
        contract_name="NodeInterface",
        address=NODE_INTERFACE_ADDRESS,
        is_classic=False,
    )

    redeem_function_data = arb_retryable_tx.encodeABI(
        fn_name="redeem",
        args=[wait_res["message"].retryable_creation_id],
    )
    gas_components = n_interface.functions.gasEstimateComponents(
        arb_retryable_tx.address, False, redeem_function_data
    ).call()

    await redeem_and_test(
        setup_state,
        message=wait_res["message"],
        expected_status=0,
        gas_limit=gas_components[0] - 1000,
    )

    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_withdraws_erc20(setup_state):
    l2_token_addr = await setup_state.erc20_bridger.get_l2_erc20_address(
        setup_state.l1_token.address, setup_state.l1_signer.provider
    )

    l2_token = setup_state.erc20_bridger.get_l2_token_contract(setup_state.l2_signer.provider, l2_token_addr)

    start_balance = DEPOSIT_AMOUNT * 5
    l2_balance_start = l2_token.functions.balanceOf(setup_state.l2_signer.account.address).call()

    assert str(l2_balance_start) == str(start_balance), "Unexpected L2 balance"

    await withdraw_token(
        {
            **setup_state,
            "amount": WITHDRAWAL_AMOUNT,
            "gatewayType": GatewayType.STANDARD,
            "startBalance": start_balance,
            "l1Token": load_contract(
                provider=setup_state.l1_signer.provider,
                contract_name="ERC20",
                address=setup_state.l1_token.address,
                is_classic=True,
            ),
        }
    )
