import unittest
from web3 import Web3
from src.lib.utils.helper import load_contract
from src.lib.data_entities.constants import (
    ARB_RETRYABLE_TX_ADDRESS,
    NODE_INTERFACE_ADDRESS,
)
from .test_helpers import (
    deposit_token,
    fund_l1,
    fund_l2,
    GatewayType,
    withdraw_token,
    mint_tokens,
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.message.l1_to_l2_message import L1ToL2MessageWriter, L1ToL2MessageStatus
from src.scripts.test_setup import test_setup
from src.lib.utils.lib import is_defined
import pytest
import json
from src.lib.utils.lib import get_transaction_receipt
from .test_helpers import deploy_test_erc20

pytestmark = pytest.mark.asyncio

# Constants similar to depositAmount and withdrawalAmount
DEPOSIT_AMOUNT = 100
WITHDRAWAL_AMOUNT = 10


@pytest.fixture
async def setup_state():
    setup = await test_setup()
    # print(setup)
    fund_l1(setup.l1_signer)
    fund_l2(setup.l2_signer)

    contract = deploy_test_erc20(
        setup.l1_signer.provider, setup.l1_signer.account
    )
    print("deployed_erc20_address", contract)

    # # Mint tokens
    mint_receipt = mint_tokens(
        setup.l1_signer.provider, contract, setup.l1_signer.account
    )
    print("mint_receipt", mint_receipt)

    # # Add the contract address to the setup
    setup["l1_token_address"] = contract.address
    return setup


# passing
@pytest.mark.asyncio
async def test_deposit_erc20(setup_state) -> None:
    await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.REDEEMED,
        expected_gateway_type=GatewayType.STANDARD,
    )


@pytest.mark.asyncio
async def redeem_and_test(
    setup_state, message: L1ToL2MessageWriter, expected_status: int, gas_limit=None
):
    manual_redeem = await message.redeem(overrides={"gasLimit": gas_limit})
    retry_rec = await manual_redeem.wait_for_redeem()
    redeem_rec = await manual_redeem.wait()
    block_hash = redeem_rec.blockHash
    print("retry_rec", retry_rec)
    assert retry_rec.blockHash == block_hash, "redeemed in same block"
    assert (
        retry_rec.to == setup_state["l2Network"]["tokenBridge"]["l2ERC20Gateway"]
    ), "redeemed in same block"
    assert retry_rec.status == expected_status, "tx didn't fail"
    assert await message.status() == (
        L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2
        if expected_status == 0
        else L1ToL2MessageStatus.REDEEMED
    ), "message status"


@pytest.mark.asyncio
async def test_deposit_with_no_funds_manual_redeem(setup_state):
    # Assuming setup_state is a fixture that sets up the test environment
    wait_res = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={
            "gasLimit": {
                "base": 0
            },  # Assuming this is the equivalent of { base: BigNumber.from(0) }
            "maxFeePerGas": {
                "base": 0
            },  # Assuming this is the equivalent of { base: BigNumber.from(0) }
        },
    )
    # Call the previously defined redeem_and_test function with the message and expected status
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_low_funds_manual_redeem(setup_state):
    # Deposit token with low gas funds
    wait_res = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
    )
    # Attempt to manually redeem
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_only_low_gas_limit_manual_redeem_success(setup_state):
    wait_res = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 21000}},
    )

    retryable_creation = await wait_res["message"].get_retryable_creation_receipt()
    if not is_defined(retryable_creation):
        raise ArbSdkError("Missing retryable creation.")

    l2_receipt = L2TransactionReceipt(retryable_creation)
    redeems_scheduled = l2_receipt.get_redeem_scheduled_events(
        provider=setup_state.l2_signer.provider
    )
    assert len(redeems_scheduled) == 1, "Unexpected redeem length"
    print("reee", redeems_scheduled[0])
    retry_receipt = await get_transaction_receipt(
        tx_hash=redeems_scheduled[0]["retryTxHash"],
        web3_instance=setup_state.l2_signer.provider,
    )
    assert retry_receipt is None, "Retry should not exist"

    # Attempt manual redeem
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_deposit_with_low_funds_fails_first_redeem_then_succeeds(setup_state):
    wait_res = await deposit_token(
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer,
        l2_signer=setup_state.l2_signer,
        expected_status=L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
        expected_gateway_type=GatewayType.STANDARD,
        retryable_overrides={"gasLimit": {"base": 5}, "maxFeePerGas": {"base": 5}},
    )

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
    )  # also available in classic!

    # Prepare the data for the 'redeem' function call
    redeem_function_data = arb_retryable_tx.functions.redeem(
        wait_res["message"].retryable_creation_id
    ).build_transaction({"from": setup_state.l2_signer.account.address})["data"]
    print("redeem_function_data", redeem_function_data)
    # Making a static call to the 'gasEstimateComponents' function
    gas_components = n_interface.functions.gasEstimateComponents(
        arb_retryable_tx.address, False, redeem_function_data
    ).call()
    print("gas_components", gas_components)
    # gasEstimate: BigNumber;
    # gasEstimateForL1: BigNumber;
    # baseFee: BigNumber;
    # l1BaseFeeEstimate: BigNumber;
    await redeem_and_test(
        setup_state,
        message=wait_res["message"],
        expected_status=0,
        gas_limit=gas_components[0] - 1000,
    )
    # Attempt another redeem which should succeed
    await redeem_and_test(setup_state, message=wait_res["message"], expected_status=1)


@pytest.mark.asyncio
async def test_withdraws_erc20(setup_state):
    print("****** l1_token_address", setup_state.l1_token_address)
    l2_token_addr = await setup_state.erc20_bridger.get_l2_erc20_address(
        setup_state.l1_token_address, setup_state.l1_signer.provider
    )
    print("****** l2_toke_address", l2_token_addr)
    l2_token = setup_state.erc20_bridger.get_l2_token_contract(
        setup_state.l2_signer.provider, l2_token_addr
    )

    # Assuming depositAmount is defined elsewhere in your tests
    start_balance = DEPOSIT_AMOUNT * 5  # Adjust based on the number of deposits
    l2_balance_start = l2_token.functions.balanceOf(
        setup_state.l2_signer.account.address
    ).call()

    assert str(l2_balance_start) == str(start_balance), "Unexpected L2 balance"

    await withdraw_token(
        {
            **setup_state,
            "amount": WITHDRAWAL_AMOUNT,  # Assuming withdrawalAmount is defined
            "gatewayType": GatewayType.STANDARD,
            "startBalance": start_balance,
            "l1Token": load_contract(
                provider=setup_state.l1_signer.provider,
                contract_name="ERC20",
                address=setup_state.l1_token_address,
                is_classic=True,  # Change based on your network type
            ),
        }
    )

    # def test_withdraws_erc20(self):
    #     l2_token_addr = self.erc20Bridger.get_l2_erc20_address(self.l1Token.address, self.l1Signer.provider)
    #     l2_token = self.erc20Bridger.get_l2_token_contract(self.l2Signer.provider, l2_token_addr)
    #     start_balance = deposit_amount * 5  # 5 deposits above - increase this number if more deposit tests added
    #     l2_balance_start = l2_token.functions.balanceOf(self.l2Signer.address).call()
    #     self.assertEqual(l2_balance_start, start_balance, 'l2 balance start')

    #     withdraw_token({
    #         'testState': testState,
    #         'amount': withdrawalAmount,
    #         'gatewayType': GatewayType.STANDARD,
    #         'startBalance': start_balance,
    #         'l1Token': load_contract(self.l1Signer.provider, 'ERC20', self.l1Token.address),
    #     })
