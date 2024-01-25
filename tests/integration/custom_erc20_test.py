import pytest
from web3 import Web3, constants
from src.lib.utils.helper import is_contract_deployed, load_contract
from .test_helpers import (
    deploy_abi_contract,
    deposit_token,
    fund_l1,
    fund_l2,
    skip_if_mainnet,
    GatewayType,
    withdraw_token,
    mint_tokens
)
from src.scripts.test_setup import test_setup
from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus

DEPOSIT_AMOUNT = 100
WITHDRAWAL_AMOUNT = 10

@pytest.mark.asyncio
async def register_custom_token(l2_network, l1_signer, l2_signer, admin_erc20_bridger):
    # # Deploy L1 custom token
    # l1_custom_token_fac = load_contract(
    #     provider=l1_signer.provider, contract_name="TestCustomTokenL1", is_classic=True
    # )
    # l1_custom_token = await l1_custom_token_fac.constructor(
    #     l2_network.token_bridge.l1_custom_gateway,
    #     l2_network.token_bridge.l1_gateway_router
    # ).transact({"from": l1_signer.account.address})

    # await l1_signer.provider.waitForTransactionReceipt(l1_custom_token)


    l1_custom_token = deploy_abi_contract(provider=l1_signer.provider, contract_name="TestCustomTokenL1", is_classic=True, deployer=l1_signer.account,
                        constructor_args=[l2_network.token_bridge.l1_custom_gateway, l2_network.token_bridge.l1_gateway_router])

    if not is_contract_deployed(l1_signer.provider, l1_custom_token.address):
        raise ArbSdkError("L1 custom token not deployed")
    
    # # Deploy L2 custom token
    # l2_custom_token_fac = load_contract(
    #     l2_signer.provider, contract_name="TestArbCustomToken", is_classic=True
    # )
    # l2_custom_token = await l2_custom_token_fac.constructor(
    #     l2_network.token_bridge.l2_custom_gateway,
    #     l1_custom_token.address
    # ).transact({"from": l2_signer.account.address})

    # await l2_signer.provider.waitForTransactionReceipt(l2_custom_token)


    l2_custom_token = deploy_abi_contract(provider=l2_signer.provider, contract_name="TestArbCustomToken", is_classic=True, deployer=l2_signer.account,
                        constructor_args=[l2_network.token_bridge.l2_custom_gateway, l1_custom_token.address])

    if not is_contract_deployed(l2_signer.provider, l2_custom_token.address):
        raise ArbSdkError("L2 custom token not deployed")

    # Attach to gateways and routers
    l1_gateway_router = load_contract(
        provider=l1_signer.provider, contract_name="L1GatewayRouter", address=l2_network.token_bridge.l1_gateway_router, is_classic=True
    )
    l2_gateway_router = load_contract(
        provider=l2_signer.provider, contract_name="L2GatewayRouter", address=l2_network.token_bridge.l2_gateway_router, is_classic=True
    )
    l1_custom_gateway = load_contract(
        provider=l1_signer.provider, contract_name="L1CustomGateway", address=l2_network.token_bridge.l1_custom_gateway, is_classic=True
    )
    l2_custom_gateway = load_contract(
        provider=l2_signer.provider, contract_name="L1CustomGateway", address=l2_network.token_bridge.l2_custom_gateway, is_classic=True
    )

    # Check starting conditions
    start_l1_gateway_address = l1_gateway_router.functions.l1TokenToGateway(
        l1_custom_token.address
    ).call()
    assert start_l1_gateway_address == constants.ADDRESS_ZERO

    start_l2_gateway_address = l2_gateway_router.functions.l1TokenToGateway(
        l1_custom_token.address
    ).call()

    assert start_l2_gateway_address == constants.ADDRESS_ZERO

    start_l1_erc20_address = l1_custom_gateway.functions.l1ToL2Token(
        l1_custom_token.address
    ).call()
    assert start_l1_erc20_address == constants.ADDRESS_ZERO

    start_l2_erc20_address = l2_custom_gateway.functions.l1ToL2Token(
        l1_custom_token.address
    ).call()
    assert start_l2_erc20_address == constants.ADDRESS_ZERO

    # Send the registration messages
    reg_tx_receipt = await admin_erc20_bridger.register_custom_token(
        l1_custom_token.address,
        l2_custom_token.address,
        l1_signer,
        l2_signer.provider,
    )
    
    print('reg_tx_receipt', reg_tx_receipt)
    # reg_tx_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(reg_tx)
    l1_to_l2_messages = await reg_tx_receipt.get_l1_to_l2_messages(l2_signer.provider)

    assert len(l1_to_l2_messages) == 2

    # Wait for the messages status
    set_token_tx = await l1_to_l2_messages[0].wait_for_status()
    assert set_token_tx['status'] == L1ToL2MessageStatus.REDEEMED

    set_gateway_tx = await l1_to_l2_messages[1].wait_for_status()
    assert set_gateway_tx['status'] == L1ToL2MessageStatus.REDEEMED

    # Check end conditions
    end_l1_gateway_address = l1_gateway_router.functions.l1TokenToGateway(
        l1_custom_token.address
    ).call()
    assert end_l1_gateway_address == l2_network.token_bridge.l1_custom_gateway

    end_l2_gateway_address = l2_gateway_router.functions.l1TokenToGateway(
        l1_custom_token.address
    ).call()
    assert end_l2_gateway_address == l2_network.token_bridge.l2_custom_gateway

    end_l1_erc20_address = l1_custom_gateway.functions.l1ToL2Token(
        l1_custom_token.address
    ).call()
    assert end_l1_erc20_address == l1_custom_token.address

    end_l2_erc20_address = l2_custom_gateway.functions.l1ToL2Token(
        l1_custom_token.address
    ).call()
    assert end_l2_erc20_address == l1_custom_token.address

    return l1_custom_token, l2_custom_token




@pytest.fixture
async def setup_state():
    setup = await test_setup()
    fund_l1(setup.l1_signer)
    fund_l2(setup.l2_signer)

    l1_token, l2_token = await register_custom_token(
        setup.l2_network,
        setup.l1_signer,
        setup.l2_signer,
        setup.admin_erc20_bridger
    )
    setup.l1_custom_token = l1_token

    return setup


# @pytest.mark.asyncio
# async def test_register_custom_token(setup_state):
#     l1_token, l2_token = await register_custom_token(
#         setup_state.l2_network,
#         setup_state.l1_signer,
#         setup_state.l2_signer,
#         setup_state.admin_erc20_bridger
#     )
#     setup_state.l1_custom_token = l1_token

@pytest.mark.asyncio
async def test_deposit(setup_state):
    mint_tokens(setup_state.l1_signer.provider, setup_state.l1_custom_token.address, setup_state.l1_signer.account)
    await deposit_token(
        DEPOSIT_AMOUNT,
        setup_state.l1_custom_token.address,
        setup_state.admin_erc20_bridger,
        setup_state.l1_signer,
        setup_state.l2_signer,
        L1ToL2MessageStatus.REDEEMED,
        GatewayType.CUSTOM
    )


@pytest.mark.asyncio
async def test_withdraws_erc20(setup_state):
    l2_token_addr = await setup_state.admin_erc20_bridger.get_l2_erc20_address(
        setup_state.l1_custom_token.address, 
        setup_state.l1_signer.provider
    )
    l2_token = setup_state.admin_erc20_bridger.get_l2_token_contract(
        setup_state.l2_signer.provider, 
        l2_token_addr
    )

    # Adjust based on the number of deposits
    start_balance = DEPOSIT_AMOUNT * 5
    l2_balance_start = l2_token.functions.balanceOf(
        setup_state.l2_signer.account.address
    ).call()

    assert str(l2_balance_start) == str(start_balance), "Unexpected L2 balance"

    await withdraw_token(
        {
            **setup_state,
            "amount": WITHDRAWAL_AMOUNT,
            "gatewayType": GatewayType.CUSTOM,
            "startBalance": start_balance,
            "l1Token": load_contract(
                provider=setup_state.l1_signer.provider,
                contract_name="ERC20",
                address=setup_state.l1_custom_token.address,
                is_classic=True,  # Adjust based on your network type
            ),
        }
    )

