import pytest
from eth_account import Account
from web3 import Web3, constants

from scripts.test_setup import setup_testing_env
from arbitrum_py.data_entities.networks import assert_arbitrum_network_has_token_bridge
from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.utils.helper import deploy_abi_contract, load_contract
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    is_arbitrum_network_with_custom_fee_token,
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
    setup_state = setup_testing_env()
    fund_parent_signer(setup_state.parent_signer)
    fund_child_signer(setup_state.child_signer)
    return setup_state


@pytest.fixture(scope="function", autouse=True)
def skip_if_mainnet(request, setup_state):
    chain_id = setup_state.child_chain.chainId
    if chain_id == 1:
        pytest.skip("Skipping test on mainnet")


def test_register_custom_token(setup_state):
    parent_token, child_token = register_custom_token(
        setup_state.child_chain,
        setup_state.parent_signer,
        setup_state.child_signer,
        setup_state.admin_erc20_bridger,
    )
    setup_state.parent_custom_token = parent_token


def test_deposit(setup_state):
    tx = setup_state.parent_custom_token.functions.mint().build_transaction(
        {"from": setup_state.parent_signer.account.address}
    )
    if "nonce" not in tx:
        tx["nonce"] = setup_state.parent_signer.provider.eth.get_transaction_count(
            setup_state.parent_signer.account.address
        )
    signed_tx = setup_state.parent_signer.account.sign_transaction(tx)
    tx_hash = setup_state.parent_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    setup_state.parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "parentTokenAddress": setup_state.parent_custom_token.address,
            "erc20Bridger": setup_state.admin_erc20_bridger,
            "parentSigner": setup_state.parent_signer,
            "childSigner": setup_state.child_signer,
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.CUSTOM,
        }
    )


def test_withdraw_token(setup_state):
    withdraw_token(
        {
            **setup_state,
            "amount": WITHDRAWAL_AMOUNT,
            "gatewayType": GatewayType.CUSTOM,
            "startBalance": DEPOSIT_AMOUNT,
            "parentToken": load_contract(
                provider=setup_state.parent_signer.provider,
                contract_name="ERC20",
                address=setup_state.parent_custom_token.address,
            ),
        }
    )


def test_deposit_with_extra_eth(setup_state):
    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "ethDepositAmount": Web3.to_wei("0.0005", "ether"),
            "parentTokenAddress": setup_state.parent_custom_token.address,
            "erc20Bridger": setup_state.admin_erc20_bridger,
            "parentSigner": setup_state.parent_signer,
            "childSigner": setup_state.child_signer,
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.CUSTOM,
        }
    )


def test_deposit_with_extra_eth_to_specific_address(setup_state):
    random_address = Account.create().address
    deposit_token(
        {
            "depositAmount": DEPOSIT_AMOUNT,
            "ethDepositAmount": Web3.to_wei("0.0005", "ether"),
            "parentTokenAddress": setup_state.parent_custom_token.address,
            "erc20Bridger": setup_state.admin_erc20_bridger,
            "parentSigner": setup_state.parent_signer,
            "childSigner": setup_state.child_signer,
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.CUSTOM,
            "destinationAddress": random_address,
        }
    )


def register_custom_token(child_chain, parent_signer, child_signer, admin_erc20_bridger):
    assert_arbitrum_network_has_token_bridge(child_chain)

    # Create custom token factories based on network type
    if is_arbitrum_network_with_custom_fee_token():
        parent_token_contract_name = "TestOrbitCustomTokenL1"
    else:
        parent_token_contract_name = "TestCustomTokenL1"

    parent_custom_token = deploy_abi_contract(
        provider=parent_signer.provider,
        contract_name=parent_token_contract_name,
        deployer=parent_signer.account,
        constructor_args=[
            child_chain.token_bridge.parent_custom_gateway,
            child_chain.token_bridge.parent_gateway_router,
        ],
    )

    # is_registered = admin_erc20_bridger.is_registered({
    #     "erc20ParentAddress": parent_custom_token.address,
    #     "parentProvider": parent_signer.provider,
    #     "childProvider": child_signer.provider,
    # })
    #
    # assert not is_registered, "Expected token not to be registered"

    child_custom_token = deploy_abi_contract(
        provider=child_signer.provider,
        contract_name="TestArbCustomToken",
        deployer=child_signer.account,
        constructor_args=[
            child_chain.token_bridge.child_custom_gateway,
            parent_custom_token.address,
        ],
    )

    # Load gateway contracts
    parent_gateway_router = load_contract(
        provider=parent_signer.provider,
        contract_name="L1GatewayRouter",
        address=child_chain.token_bridge.parent_gateway_router,
    )
    child_gateway_router = load_contract(
        provider=child_signer.provider,
        contract_name="L2GatewayRouter",
        address=child_chain.token_bridge.child_gateway_router,
    )
    parent_custom_gateway = load_contract(
        provider=parent_signer.provider,
        contract_name="L1CustomGateway",
        address=child_chain.token_bridge.parent_custom_gateway,
    )
    child_custom_gateway = load_contract(
        provider=child_signer.provider,
        contract_name="L1CustomGateway",
        address=child_chain.token_bridge.child_custom_gateway,
    )

    # Check starting conditions
    start_parent_gateway_address = parent_gateway_router.functions.l1TokenToGateway(parent_custom_token.address).call()
    assert start_parent_gateway_address == constants.ADDRESS_ZERO

    start_child_gateway_address = child_gateway_router.functions.l1TokenToGateway(parent_custom_token.address).call()
    assert start_child_gateway_address == constants.ADDRESS_ZERO

    start_parent_erc20_address = parent_custom_gateway.functions.l1ToL2Token(parent_custom_token.address).call()
    assert start_parent_erc20_address == constants.ADDRESS_ZERO

    start_child_erc20_address = child_custom_gateway.functions.l1ToL2Token(parent_custom_token.address).call()
    assert start_child_erc20_address == constants.ADDRESS_ZERO

    # Test approve gas token if needed
    if is_arbitrum_network_with_custom_fee_token():
        try:
            reg_tx_receipt = admin_erc20_bridger.register_custom_token(
                parent_custom_token.address,
                child_custom_token.address,
                parent_signer,
                child_signer.provider,
            )
            reg_tx_receipt.wait()
            raise AssertionError("Child custom token is not approved but got deployed")
        except Exception as err:
            assert "Insufficient allowance" in str(err)

        admin_erc20_bridger.approve_gas_token_for_custom_token_registration(
            {
                "parentSigner": parent_signer,
                "erc20ParentAddress": parent_custom_token.address,
            }
        )

    # Register token
    reg_tx_receipt = admin_erc20_bridger.register_custom_token(
        parent_custom_token.address,
        child_custom_token.address,
        parent_signer,
        child_signer.provider,
    )

    parent_to_child_messages = reg_tx_receipt.get_parent_to_child_messages(child_signer.provider)
    assert len(parent_to_child_messages) == 2

    set_token_tx = parent_to_child_messages[0].wait_for_status()
    assert set_token_tx["status"] == ParentToChildMessageStatus.REDEEMED

    set_gateway_tx = parent_to_child_messages[1].wait_for_status()
    assert set_gateway_tx["status"] == ParentToChildMessageStatus.REDEEMED

    # Check end conditions
    end_parent_gateway_address = parent_gateway_router.functions.l1TokenToGateway(parent_custom_token.address).call()
    assert end_parent_gateway_address == child_chain.token_bridge.parent_custom_gateway

    end_child_gateway_address = child_gateway_router.functions.l1TokenToGateway(parent_custom_token.address).call()
    assert end_child_gateway_address == child_chain.token_bridge.child_custom_gateway

    end_parent_erc20_address = parent_custom_gateway.functions.l1ToL2Token(parent_custom_token.address).call()
    assert end_parent_erc20_address == child_custom_token.address

    end_child_erc20_address = child_custom_gateway.functions.l1ToL2Token(parent_custom_token.address).call()
    assert end_child_erc20_address == child_custom_token.address

    is_registered = admin_erc20_bridger.is_registered(
        {
            "erc20ParentAddress": parent_custom_token.address,
            "parentProvider": parent_signer.provider,
            "childProvider": child_signer.provider,
        }
    )
    assert is_registered, "Expected token to be registered"

    return parent_custom_token, child_custom_token
