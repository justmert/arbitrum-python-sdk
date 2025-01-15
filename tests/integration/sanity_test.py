import os

from scripts.test_setup import setup_testing_env
from arbitrum_py.utils.helper import load_contract
from tests.integration.custom_fee_token.mocha_extensions import it_only_when_eth


def expect_ignore_case(expected, actual):
    assert expected.lower() == actual.lower()


def test_standard_gateways_public_storage_vars_properly_set():
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain

    parent_gateway = load_contract(
        contract_name="L1ERC20Gateway",
        address=child_chain.token_bridge.parent_erc20_gateway,
        provider=parent_signer.provider,
    )
    child_gateway = load_contract(
        contract_name="L2ERC20Gateway",
        address=child_chain.token_bridge.child_erc20_gateway,
        provider=child_signer.provider,
    )

    parent_clonable_proxy_hash = parent_gateway.functions.cloneableProxyHash().call()
    child_clonable_proxy_hash = child_gateway.functions.cloneableProxyHash().call()
    assert parent_clonable_proxy_hash == child_clonable_proxy_hash

    parent_beacon_proxy_hash = parent_gateway.functions.l2BeaconProxyFactory().call()
    child_beacon_proxy_hash = child_gateway.functions.beaconProxyFactory().call()
    assert parent_beacon_proxy_hash == child_beacon_proxy_hash

    parent_gateway_counterparty = parent_gateway.functions.counterpartGateway().call()
    expect_ignore_case(parent_gateway_counterparty, child_chain.token_bridge.child_erc20_gateway)

    child_gateway_counterparty = child_gateway.functions.counterpartGateway().call()
    expect_ignore_case(child_gateway_counterparty, child_chain.token_bridge.parent_erc20_gateway)

    parent_router = parent_gateway.functions.router().call()
    expect_ignore_case(parent_router, child_chain.token_bridge.parent_gateway_router)

    child_router = child_gateway.functions.router().call()
    expect_ignore_case(child_router, child_chain.token_bridge.child_gateway_router)


def test_custom_gateways_public_storage_vars_properly_set():
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain

    parent_custom_gateway = load_contract(
        contract_name="L1CustomGateway",
        address=child_chain.token_bridge.parent_custom_gateway,
        provider=parent_signer.provider,
    )
    child_custom_gateway = load_contract(
        contract_name="L2CustomGateway",
        address=child_chain.token_bridge.child_custom_gateway,
        provider=child_signer.provider,
    )

    parent_gateway_counterparty = parent_custom_gateway.functions.counterpartGateway().call()
    expect_ignore_case(parent_gateway_counterparty, child_chain.token_bridge.child_custom_gateway)

    child_gateway_counterparty = child_custom_gateway.functions.counterpartGateway().call()
    expect_ignore_case(child_gateway_counterparty, child_chain.token_bridge.parent_custom_gateway)

    parent_router = parent_custom_gateway.functions.router().call()
    expect_ignore_case(parent_router, child_chain.token_bridge.parent_gateway_router)

    child_router = child_custom_gateway.functions.router().call()
    expect_ignore_case(child_router, child_chain.token_bridge.child_gateway_router)


@it_only_when_eth
def test_weth_gateways_gateways_public_storage_vars_properly_set():
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain

    parent_weth_gateway = load_contract(
        contract_name="L1WethGateway",
        address=child_chain.token_bridge.parent_weth_gateway,
        provider=parent_signer.provider,
    )
    child_weth_gateway = load_contract(
        contract_name="L2WethGateway",
        address=child_chain.token_bridge.child_weth_gateway,
        provider=child_signer.provider,
    )

    parent_weth = parent_weth_gateway.functions.l1Weth().call()
    expect_ignore_case(parent_weth, child_chain.token_bridge.parent_weth)

    child_weth = child_weth_gateway.functions.l2Weth().call()
    expect_ignore_case(child_weth, child_chain.token_bridge.child_weth)

    parent_gateway_counterparty = parent_weth_gateway.functions.counterpartGateway().call()
    expect_ignore_case(parent_gateway_counterparty, child_chain.token_bridge.child_weth_gateway)

    child_gateway_counterparty = child_weth_gateway.functions.counterpartGateway().call()
    expect_ignore_case(child_gateway_counterparty, child_chain.token_bridge.parent_weth_gateway)

    parent_router = parent_weth_gateway.functions.router().call()
    expect_ignore_case(parent_router, child_chain.token_bridge.parent_gateway_router)

    child_router = child_weth_gateway.functions.router().call()
    expect_ignore_case(child_router, child_chain.token_bridge.child_gateway_router)


@it_only_when_eth
def test_ae_weth_public_vars_properly_set():
    setup_state = setup_testing_env()
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain

    ae_weth = load_contract(
        contract_name="AeWETH",
        address=child_chain.token_bridge.child_weth,
        provider=child_signer.provider,
    )

    child_gateway_on_ae_weth = ae_weth.functions.l2Gateway().call()
    expect_ignore_case(child_gateway_on_ae_weth, child_chain.token_bridge.child_weth_gateway)

    parent_address_on_ae_weth = ae_weth.functions.l1Address().call()
    expect_ignore_case(parent_address_on_ae_weth, child_chain.token_bridge.parent_weth)


@it_only_when_eth
def test_parent_gateway_router_points_to_right_weth_gateways():
    setup_state = setup_testing_env()
    admin_erc20_bridger = setup_state.admin_erc20_bridger
    parent_signer = setup_state.parent_signer
    child_chain = setup_state.child_chain

    gateway = admin_erc20_bridger.get_parent_gateway_address(
        child_chain.token_bridge.parent_weth, parent_signer.provider
    )
    assert gateway == child_chain.token_bridge.parent_weth_gateway


def test_parent_and_child_implementations_of_calculate_child_erc20_address_match():
    setup_state = setup_testing_env()
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    child_chain = setup_state.child_chain
    erc20_bridger = setup_state.erc20_bridger

    address = os.urandom(20)

    erc20_child_address_as_per_parent = erc20_bridger.get_child_erc20_address(address, parent_signer.provider)
    child_gateway_router = load_contract(
        contract_name="L2GatewayRouter",
        address=child_chain.token_bridge.child_gateway_router,
        provider=child_signer.provider,
    )
    erc20_child_address_as_per_child = child_gateway_router.functions.calculateL2TokenAddress(address).call()

    assert erc20_child_address_as_per_child == erc20_child_address_as_per_parent
