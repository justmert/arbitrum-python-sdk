import os

import pytest

from src.lib.utils.helper import load_contract
from src.scripts.test_setup import test_setup


def expect_ignore_case(expected, actual):
    assert expected.lower() == actual.lower()


@pytest.mark.asyncio
async def test_standard_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1Signer"]
    l2_signer = setup_state["l2Signer"]
    l2_network = setup_state["l2Network"]

    l1_gateway = load_contract(
        contract_name="L1ERC20Gateway",
        address=l2_network["tokenBridge"]["l1ERC20Gateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )
    l2_gateway = load_contract(
        contract_name="L2ERC20Gateway",
        address=l2_network["tokenBridge"]["l2ERC20Gateway"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    l1_clonable_proxy_hash = l1_gateway.functions.cloneableProxyHash().call()
    l2_clonable_proxy_hash = l2_gateway.functions.cloneableProxyHash().call()
    assert l1_clonable_proxy_hash == l2_clonable_proxy_hash

    l1_beacon_proxy_hash = l1_gateway.functions.l2BeaconProxyFactory().call()
    l2_beacon_proxy_hash = l2_gateway.functions.beaconProxyFactory().call()
    assert l1_beacon_proxy_hash == l2_beacon_proxy_hash

    l1_gateway_counterparty = l1_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l1_gateway_counterparty, l2_network["tokenBridge"]["l2ERC20Gateway"])

    l2_gateway_counterparty = l2_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l2_gateway_counterparty, l2_network["tokenBridge"]["l1ERC20Gateway"])

    l1_router = l1_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["tokenBridge"]["l1GatewayRouter"])

    l2_router = l2_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["tokenBridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_custom_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1Signer"]
    l2_signer = setup_state["l2Signer"]
    l2_network = setup_state["l2Network"]

    l1_custom_gateway = load_contract(
        contract_name="L1CustomGateway",
        address=l2_network["tokenBridge"]["l1CustomGateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )
    l2_custom_gateway = load_contract(
        contract_name="L2CustomGateway",
        address=l2_network["tokenBridge"]["l2CustomGateway"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    l1_gateway_counterparty = l1_custom_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l1_gateway_counterparty, l2_network["tokenBridge"]["l2CustomGateway"])

    l2_gateway_counterparty = l2_custom_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l2_gateway_counterparty, l2_network["tokenBridge"]["l1CustomGateway"])

    l1_router = l1_custom_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["tokenBridge"]["l1GatewayRouter"])

    l2_router = l2_custom_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["tokenBridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_weth_gateways_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1Signer"]
    l2_signer = setup_state["l2Signer"]
    l2_network = setup_state["l2Network"]

    l1_weth_gateway = load_contract(
        contract_name="L1WethGateway",
        address=l2_network["tokenBridge"]["l1WethGateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )

    l2_weth_gateway = load_contract(
        contract_name="L2WethGateway",
        address=l2_network["tokenBridge"]["l2WethGateway"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    l1_weth = l1_weth_gateway.functions.l1Weth().call()
    expect_ignore_case(l1_weth, l2_network["tokenBridge"]["l1Weth"])

    l2_weth = l2_weth_gateway.functions.l2Weth().call()
    expect_ignore_case(l2_weth, l2_network["tokenBridge"]["l2Weth"])

    l1_gateway_counterparty = l1_weth_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l1_gateway_counterparty, l2_network["tokenBridge"]["l2WethGateway"])

    l2_gateway_counterparty = l2_weth_gateway.functions.counterpartGateway().call()
    expect_ignore_case(l2_gateway_counterparty, l2_network["tokenBridge"]["l1WethGateway"])

    l1_router = l1_weth_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["tokenBridge"]["l1GatewayRouter"])

    l2_router = l2_weth_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["tokenBridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_ae_weth_public_vars_properly_set():
    setup_state = await test_setup()
    l2_signer = setup_state["l2Signer"]
    l2_network = setup_state["l2Network"]

    ae_weth = load_contract(
        contract_name="AeWETH",
        address=l2_network["tokenBridge"]["l2Weth"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    l2_gateway_on_ae_weth = ae_weth.functions.l2Gateway().call()
    expect_ignore_case(l2_gateway_on_ae_weth, l2_network["tokenBridge"]["l2WethGateway"])

    l1_address_on_ae_weth = ae_weth.functions.l1Address().call()
    expect_ignore_case(l1_address_on_ae_weth, l2_network["tokenBridge"]["l1Weth"])


@pytest.mark.asyncio
async def test_l1_gateway_router_points_to_right_weth_gateways():
    setup_state = await test_setup()
    admin_erc20_bridger = setup_state["adminERC20Bridger"]
    l1_signer = setup_state["l1Signer"]
    l2_network = setup_state["l2Network"]

    gateway = await admin_erc20_bridger.get_l1_gateway_address(l2_network["tokenBridge"]["l1Weth"], l1_signer.provider)

    assert gateway == l2_network["tokenBridge"]["l1WethGateway"]


@pytest.mark.asyncio
async def test_l1_and_l2_implementations_of_calculate_l2_erc20_address_match():
    setup_state = await test_setup()
    l1_signer = setup_state["l1Signer"]
    l2_signer = setup_state["l2Signer"]
    l2_network = setup_state["l2Network"]
    erc20_bridger = setup_state["erc20Bridger"]

    address = os.urandom(20)

    erc20_l2_address_as_per_l1 = await erc20_bridger.get_l2_erc20_address(address, l1_signer.provider)
    l2_gateway_router = load_contract(
        contract_name="L2GatewayRouter",
        address=l2_network["tokenBridge"]["l2GatewayRouter"],
        provider=l2_signer.provider,
        is_classic=True,
    )
    erc20_l2_address_as_per_l2 = l2_gateway_router.functions.calculateL2TokenAddress(address).call()

    assert erc20_l2_address_as_per_l2 == erc20_l2_address_as_per_l1
