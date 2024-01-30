import pytest
from web3 import Web3
from eth_account import Account
from src.lib.utils.helper import load_contract
from src.scripts.test_setup import test_setup
from web3.exceptions import ContractLogicError
import os
import random


def expect_ignore_case(expected: str, actual: str):
    assert expected.lower() == actual.lower()


@pytest.mark.asyncio
async def test_standard_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1_signer"]
    l2_signer = setup_state["l2_signer"]
    l2_network = setup_state["l2_network"]

    l1_gateway = load_contract(
        contract_name="L1ERC20Gateway",
        address=l2_network["token_bridge"]["l1ERC20Gateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )
    l2_gateway = load_contract(
        contract_name="L2ERC20Gateway",
        address=l2_network["token_bridge"]["l2ERC20Gateway"],
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
    expect_ignore_case(
        l1_gateway_counterparty, l2_network["token_bridge"]["l2ERC20Gateway"]
    )

    l2_gateway_counterparty = l2_gateway.functions.counterpartGateway().call()
    expect_ignore_case(
        l2_gateway_counterparty, l2_network["token_bridge"]["l1ERC20Gateway"]
    )

    l1_router = l1_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["token_bridge"]["l1GatewayRouter"])

    l2_router = l2_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["token_bridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_custom_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1_signer"]
    l2_signer = setup_state["l2_signer"]
    l2_network = setup_state["l2_network"]

    l1_custom_gateway = load_contract(
        contract_name="L1CustomGateway",
        address=l2_network["token_bridge"]["l1CustomGateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )
    l2_custom_gateway = load_contract(
        contract_name="L2CustomGateway",
        address=l2_network["token_bridge"]["l2CustomGateway"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    l1_gateway_counterparty = (
        l1_custom_gateway.functions.counterpartGateway().call()
    )
    expect_ignore_case(
        l1_gateway_counterparty, l2_network["token_bridge"]["l2CustomGateway"]
    )

    l2_gateway_counterparty = (
        l2_custom_gateway.functions.counterpartGateway().call()
    )
    expect_ignore_case(
        l2_gateway_counterparty, l2_network["token_bridge"]["l1CustomGateway"]
    )

    l1_router = l1_custom_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["token_bridge"]["l1GatewayRouter"])

    l2_router = l2_custom_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["token_bridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_weth_gateways_gateways_public_storage_vars_properly_set():
    setup_state = await test_setup()
    l1_signer = setup_state["l1_signer"]
    l2_signer = setup_state["l2_signer"]
    l2_network = setup_state["l2_network"]

    # L1 Weth Gateway
    l1_weth_gateway = load_contract(
        contract_name="L1WethGateway",
        address=l2_network["token_bridge"]["l1WethGateway"],
        provider=l1_signer.provider,
        is_classic=True,
    )

    # L2 Weth Gateway
    l2_weth_gateway = load_contract(
        contract_name="L2WethGateway",
        address=l2_network["token_bridge"]["l2WethGateway"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    # Check L1 Weth address
    l1_weth = l1_weth_gateway.functions.l1Weth().call()
    expect_ignore_case(l1_weth, l2_network["token_bridge"]["l1Weth"])

    # Check L2 Weth address
    l2_weth = l2_weth_gateway.functions.l2Weth().call()
    expect_ignore_case(l2_weth, l2_network["token_bridge"]["l2Weth"])

    # Check counterpart gateways
    l1_gateway_counterparty = (
        l1_weth_gateway.functions.counterpartGateway().call()
    )
    expect_ignore_case(
        l1_gateway_counterparty, l2_network["token_bridge"]["l2WethGateway"]
    )

    l2_gateway_counterparty = (
        l2_weth_gateway.functions.counterpartGateway().call()
    )
    expect_ignore_case(
        l2_gateway_counterparty, l2_network["token_bridge"]["l1WethGateway"]
    )

    # Check routers
    l1_router = l1_weth_gateway.functions.router().call()
    expect_ignore_case(l1_router, l2_network["token_bridge"]["l1GatewayRouter"])

    l2_router = l2_weth_gateway.functions.router().call()
    expect_ignore_case(l2_router, l2_network["token_bridge"]["l2GatewayRouter"])


@pytest.mark.asyncio
async def test_ae_weth_public_vars_properly_set():
    setup_state = await test_setup()
    l2_signer = setup_state["l2_signer"]
    l2_network = setup_state["l2_network"]

    # AeWETH contract
    ae_weth = load_contract(
        contract_name="AeWETH",
        address=l2_network["token_bridge"]["l2Weth"],
        provider=l2_signer.provider,
        is_classic=True,
    )

    # Check L2 Gateway on AeWETH
    l2_gateway_on_ae_weth = ae_weth.functions.l2Gateway().call()
    expect_ignore_case(
        l2_gateway_on_ae_weth, l2_network["token_bridge"]["l2WethGateway"]
    )

    # Check L1 Address on AeWETH
    l1_address_on_ae_weth = ae_weth.functions.l1Address().call()
    expect_ignore_case(l1_address_on_ae_weth, l2_network["token_bridge"]["l1Weth"])


@pytest.mark.asyncio
async def test_l1_gateway_router_points_to_right_weth_gateways():
    setup_state = await test_setup()
    admin_erc20_bridger = setup_state["admin_erc20_bridger"]
    l1_signer = setup_state["l1_signer"]
    l2_network = setup_state["l2_network"]

    # Get the gateway address for L1 WETH from the L1 ERC20 Bridger
    gateway = await admin_erc20_bridger.get_l1_gateway_address(
        l2_network["token_bridge"]["l1Weth"], l1_signer.provider
    )

    # Assert that the gateway address matches the L1 Weth Gateway address in the network configuration
    assert gateway == l2_network["token_bridge"]["l1WethGateway"]


# Example for one of the cases:
@pytest.mark.asyncio
async def test_l1_and_l2_implementations_of_calculate_l2_erc20_address_match():
    setup_state = await test_setup()
    l1_signer = setup_state["l1_signer"]
    l2_signer = setup_state["l2_signer"]
    l2_network = setup_state["l2_network"]
    erc20_bridger = setup_state["erc20_bridger"]

    address = os.urandom(20)

    erc20_l2_address_as_per_l1 = await erc20_bridger.get_l2_erc20_address(
        address, l1_signer.provider
    )
    l2_gateway_router = load_contract(
        contract_name="L2GatewayRouter",
        address=l2_network["token_bridge"]["l2GatewayRouter"],
        provider=l2_signer.provider,
        is_classic=True,
    )
    erc20_l2_address_as_per_l2 = (
        l2_gateway_router.functions.calculateL2TokenAddress(address).call()
    )

    assert erc20_l2_address_as_per_l2 == erc20_l2_address_as_per_l1
