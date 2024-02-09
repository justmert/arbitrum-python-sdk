import pytest
from web3 import constants

from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.utils.helper import (
    deploy_abi_contract,
    is_contract_deployed,
    load_contract,
)
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
    setup_state = await test_setup()
    fund_l1(setup_state.l1_signer)
    fund_l2(setup_state.l2_signer)
    return setup_state


@pytest.fixture(scope="function", autouse=True)
async def skip_if_mainnet(request, setup_state):
    chain_id = setup_state.l1_network.chain_id
    if chain_id == 1:
        pytest.skip("Skipping test on mainnet")


@pytest.mark.asyncio
async def test_register_custom_token(setup_state):
    l1_token, l2_token = await register_custom_token(
        setup_state.l2_network, setup_state.l1_signer, setup_state.l2_signer, setup_state.admin_erc20_bridger
    )
    setup_state.l1_custom_token = l1_token


@pytest.mark.asyncio
async def test_deposit(setup_state):
    tx_hash = setup_state.l1_custom_token.functions.mint().transact({"from": setup_state.l1_signer.account.address})

    setup_state.l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    await deposit_token(
        DEPOSIT_AMOUNT,
        setup_state.l1_custom_token.address,
        setup_state.admin_erc20_bridger,
        setup_state.l1_signer,
        setup_state.l2_signer,
        L1ToL2MessageStatus.REDEEMED,
        GatewayType.CUSTOM,
    )


@pytest.mark.asyncio
async def test_withdraw_token(setup_state):
    await withdraw_token(
        {
            **setup_state,
            "amount": DEPOSIT_AMOUNT,
            "gatewayType": GatewayType.CUSTOM,
            "startBalance": DEPOSIT_AMOUNT,
            "l1Token": load_contract(
                provider=setup_state.l1_signer.provider,
                contract_name="ERC20",
                address=setup_state.l1_custom_token.address,
                is_classic=True,
            ),
        }
    )


@pytest.mark.asyncio
async def register_custom_token(l2_network, l1_signer, l2_signer, admin_erc20_bridger):
    l1_custom_token = deploy_abi_contract(
        provider=l1_signer.provider,
        contract_name="TestCustomTokenL1",
        is_classic=True,
        deployer=l1_signer.account,
        constructor_args=[l2_network.token_bridge.l1_custom_gateway, l2_network.token_bridge.l1_gateway_router],
    )

    if not is_contract_deployed(l1_signer.provider, l1_custom_token.address):
        raise ArbSdkError("L1 custom token not deployed")

    l2_custom_token = deploy_abi_contract(
        provider=l2_signer.provider,
        contract_name="TestArbCustomToken",
        is_classic=True,
        deployer=l2_signer.account,
        constructor_args=[l2_network.token_bridge.l2_custom_gateway, l1_custom_token.address],
    )

    if not is_contract_deployed(l2_signer.provider, l2_custom_token.address):
        raise ArbSdkError("L2 custom token not deployed")

    l1_gateway_router = load_contract(
        provider=l1_signer.provider,
        contract_name="L1GatewayRouter",
        address=l2_network.token_bridge.l1_gateway_router,
        is_classic=True,
    )
    l2_gateway_router = load_contract(
        provider=l2_signer.provider,
        contract_name="L2GatewayRouter",
        address=l2_network.token_bridge.l2_gateway_router,
        is_classic=True,
    )
    l1_custom_gateway = load_contract(
        provider=l1_signer.provider,
        contract_name="L1CustomGateway",
        address=l2_network.token_bridge.l1_custom_gateway,
        is_classic=True,
    )
    l2_custom_gateway = load_contract(
        provider=l2_signer.provider,
        contract_name="L1CustomGateway",
        address=l2_network.token_bridge.l2_custom_gateway,
        is_classic=True,
    )

    start_l1_gateway_address = l1_gateway_router.functions.l1TokenToGateway(l1_custom_token.address).call()
    assert start_l1_gateway_address == constants.ADDRESS_ZERO

    start_l2_gateway_address = l2_gateway_router.functions.l1TokenToGateway(l1_custom_token.address).call()

    assert start_l2_gateway_address == constants.ADDRESS_ZERO

    start_l1_erc20_address = l1_custom_gateway.functions.l1ToL2Token(l1_custom_token.address).call()
    assert start_l1_erc20_address == constants.ADDRESS_ZERO

    start_l2_erc20_address = l2_custom_gateway.functions.l1ToL2Token(l1_custom_token.address).call()
    assert start_l2_erc20_address == constants.ADDRESS_ZERO

    reg_tx_receipt = await admin_erc20_bridger.register_custom_token(
        l1_custom_token.address,
        l2_custom_token.address,
        l1_signer,
        l2_signer.provider,
    )

    l1_to_l2_messages = await reg_tx_receipt.get_l1_to_l2_messages(l2_signer.provider)

    assert len(l1_to_l2_messages) == 2

    set_token_tx = await l1_to_l2_messages[0].wait_for_status()
    assert set_token_tx["status"] == L1ToL2MessageStatus.REDEEMED

    set_gateway_tx = await l1_to_l2_messages[1].wait_for_status()
    assert set_gateway_tx["status"] == L1ToL2MessageStatus.REDEEMED

    end_l1_gateway_address = l1_gateway_router.functions.l1TokenToGateway(l1_custom_token.address).call()
    assert end_l1_gateway_address == l2_network.token_bridge.l1_custom_gateway

    end_l2_gateway_address = l2_gateway_router.functions.l1TokenToGateway(l1_custom_token.address).call()
    assert end_l2_gateway_address == l2_network.token_bridge.l2_custom_gateway

    end_l1_erc20_address = l1_custom_gateway.functions.l1ToL2Token(l1_custom_token.address).call()
    assert end_l1_erc20_address == l2_custom_token.address

    end_l2_erc20_address = l2_custom_gateway.functions.l1ToL2Token(l1_custom_token.address).call()
    assert end_l2_erc20_address == l2_custom_token.address

    return l1_custom_token, l2_custom_token
