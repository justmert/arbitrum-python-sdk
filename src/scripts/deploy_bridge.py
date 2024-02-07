from src.lib.data_entities.constants import ADDRESS_ZERO
from src.lib.utils.helper import deploy_abi_contract, load_abi


def deploy_behind_proxy(deployer, contract_name, admin, data_to_call_proxy="0x", is_classic=False):
    instance = deploy_abi_contract(deployer.provider, deployer.account, contract_name, is_classic=is_classic)

    contract_abi, _ = load_abi(contract_name, is_classic=is_classic)

    proxy = deploy_abi_contract(
        provider=deployer.provider,
        deployer=deployer.account,
        contract_name="TransparentUpgradeableProxy",
        constructor_args=[instance.address, admin.address, data_to_call_proxy],
        is_classic=is_classic,
    )
    return deployer.provider.eth.contract(address=proxy.address, abi=contract_abi)


def deploy_erc20_l1(deployer):
    provider = deployer.provider
    proxy_admin = deploy_abi_contract(provider, deployer, "ProxyAdmin", is_classic=False)
    print("proxy admin address", proxy_admin.address)
    router = deploy_behind_proxy(deployer, "L1GatewayRouter", proxy_admin, is_classic=True)
    print("router address", router.address)
    standard_gateway = deploy_behind_proxy(deployer, "L1ERC20Gateway", proxy_admin, is_classic=True)
    print("standard gateway address", standard_gateway.address)
    custom_gateway = deploy_behind_proxy(deployer, "L1CustomGateway", proxy_admin, is_classic=True)
    print("custom gateway address", custom_gateway.address)
    weth_gateway = deploy_behind_proxy(deployer, "L1WethGateway", proxy_admin, is_classic=True)
    print("weth gateway address", weth_gateway.address)
    weth = deploy_abi_contract(provider, deployer, "TestWETH9", ["WETH", "WETH"], is_classic=True)
    print("weth address", weth.address)
    multicall = deploy_abi_contract(provider, deployer, "Multicall2", is_classic=True)
    print("multicall address", multicall.address)

    return {
        "proxyAdmin": proxy_admin,
        "router": router,
        "standardGateway": standard_gateway,
        "customGateway": custom_gateway,
        "wethGateway": weth_gateway,
        "weth": weth,
        "multicall": multicall,
    }


def deploy_erc20_l2(deployer):
    provider = deployer.provider

    proxy_admin = deploy_abi_contract(provider, deployer, "ProxyAdmin", is_classic=False)
    print("proxy admin address", proxy_admin.address)
    router = deploy_behind_proxy(deployer, "L2GatewayRouter", proxy_admin, is_classic=True)
    print("router address", router.address)
    standard_gateway = deploy_behind_proxy(deployer, "L2ERC20Gateway", proxy_admin, is_classic=True)
    print("standard gateway address", standard_gateway.address)
    custom_gateway = deploy_behind_proxy(deployer, "L2CustomGateway", proxy_admin, is_classic=True)
    print("custom gateway address", custom_gateway.address)
    weth_gateway = deploy_behind_proxy(deployer, "L2WethGateway", proxy_admin, is_classic=True)
    print("weth gateway address", weth_gateway.address)

    standard_arb_erc20 = deploy_abi_contract(provider, deployer, "StandardArbERC20", is_classic=True)
    print("standard arb erc20 address", standard_arb_erc20.address)
    beacon = deploy_abi_contract(
        provider,
        deployer,
        "UpgradeableBeacon",
        [standard_arb_erc20.address],
        is_classic=False,
    )
    print("beacon address", beacon.address)
    beacon_proxy = deploy_abi_contract(provider, deployer, "BeaconProxyFactory", is_classic=True)
    print("beacon proxy address", beacon_proxy.address)

    weth = deploy_behind_proxy(deployer, "AeWETH", proxy_admin, is_classic=True)
    print("weth address", weth.address)
    multicall = deploy_abi_contract(provider, deployer, "ArbMulticall2", is_classic=True)
    print("multicall address", multicall.address)

    return {
        "proxyAdmin": proxy_admin,
        "router": router,
        "standardGateway": standard_gateway,
        "customGateway": custom_gateway,
        "wethGateway": weth_gateway,
        "beacon": beacon,
        "beaconProxyFactory": beacon_proxy,
        "weth": weth,
        "multicall": multicall,
    }


def _send_transaction_wrapper(signer, contract_function):
    tx_hash = contract_function.transact({"from": signer.account.address})
    tx_receipt = signer.provider.eth.wait_for_transaction_receipt(tx_hash)
    return tx_receipt


def deploy_erc20_and_init(l1_signer, l2_signer, inbox_address):
    print("Deploying L1 contracts...")

    l1_contracts = deploy_erc20_l1(l1_signer)

    print("Deploying L2 contracts...")
    l2_contracts = deploy_erc20_l2(l2_signer)

    print("Initializing L2 contracts...")
    _send_transaction_wrapper(
        l2_signer,
        l2_contracts["router"].functions.initialize(
            l1_contracts["router"].address, l2_contracts["standardGateway"].address
        ),
    )

    _send_transaction_wrapper(
        l2_signer, l2_contracts["beaconProxyFactory"].functions.initialize(l2_contracts["beacon"].address)
    )

    _send_transaction_wrapper(
        l2_signer,
        l2_contracts["standardGateway"].functions.initialize(
            l1_contracts["standardGateway"].address,
            l2_contracts["router"].address,
            l2_contracts["beaconProxyFactory"].address,
        ),
    )

    _send_transaction_wrapper(
        l2_signer,
        l2_contracts["customGateway"].functions.initialize(
            l1_contracts["customGateway"].address, l2_contracts["router"].address
        ),
    )

    _send_transaction_wrapper(
        l2_signer,
        l2_contracts["weth"].functions.initialize(
            "WETH",
            "WETH",
            18,
            l2_contracts["wethGateway"].address,
            l1_contracts["weth"].address,
        ),
    )

    _send_transaction_wrapper(
        l2_signer,
        l2_contracts["wethGateway"].functions.initialize(
            l1_contracts["wethGateway"].address,
            l2_contracts["router"].address,
            l1_contracts["weth"].address,
            l2_contracts["weth"].address,
        ),
    )

    print("Initializing L1 contracts...")
    _send_transaction_wrapper(
        l1_signer,
        l1_contracts["router"].functions.initialize(
            l1_signer.account.address,
            l1_contracts["standardGateway"].address,
            ADDRESS_ZERO,
            l2_contracts["router"].address,
            inbox_address,
        ),
    )

    cloneable_proxy_hash = (
        l2_signer.provider.eth.contract(
            address=l2_contracts["beaconProxyFactory"].address,
            abi=l2_contracts["beaconProxyFactory"].abi,
        )
        .functions.cloneableProxyHash()
        .call()
    )

    _send_transaction_wrapper(
        l1_signer,
        l1_contracts["standardGateway"].functions.initialize(
            l2_contracts["standardGateway"].address,
            l1_contracts["router"].address,
            inbox_address,
            cloneable_proxy_hash,
            l2_contracts["beaconProxyFactory"].address,
        ),
    )

    _send_transaction_wrapper(
        l1_signer,
        l1_contracts["customGateway"].functions.initialize(
            l2_contracts["customGateway"].address,
            l1_contracts["router"].address,
            inbox_address,
            l1_signer.account.address,
        ),
    )

    _send_transaction_wrapper(
        l1_signer,
        l1_contracts["wethGateway"].functions.initialize(
            l2_contracts["wethGateway"].address,
            l1_contracts["router"].address,
            inbox_address,
            l1_contracts["weth"].address,
            l2_contracts["weth"].address,
        ),
    )

    return l1_contracts, l2_contracts
