from web3 import Web3
from web3.contract import Contract
from eth_typing import Address
# from web3.eth import Account
from web3 import Account
import json

ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"

def load_contract_abi(name: str, is_classic = False) -> list:
    if is_classic:
        file_path = f'src/abi/classic/{name}.json'

    else:
        file_path = f'src/abi/{name}.json'

    with open(file_path, 'r') as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get('abi'):
            raise Exception(f'No ABI found for contract: {name}')
        return contract_data['abi'], contract_data.get('bytecode', '')

def deploy_contract(provider: Web3, deployer: Account, contract_name: str, *constructor_args, is_classic = False) -> Contract:
    contract_abi, bytecode = load_contract_abi(contract_name, is_classic=is_classic)
    contract = provider.eth.contract(abi=contract_abi, bytecode=bytecode)
    construct_txn = contract.constructor(*constructor_args).build_transaction({
        'from': deployer.address,
        'nonce': provider.eth.get_transaction_count(deployer.address),
        'gas': 2528712,  # You might want to estimate this value
        'gasPrice': provider.to_wei('21', 'gwei')
    })
    signed = deployer.sign_transaction(construct_txn)
    tx_hash = provider.eth.send_raw_transaction(signed.rawTransaction)
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)
    return provider.eth.contract(address=tx_receipt.contractAddress, abi=contract_abi)

def deploy_behind_proxy(provider, deployer: Account, factory_name: str, admin: Contract, data_to_call_proxy='0x', is_classic = False) -> Contract:
    contract_abi, _ = load_contract_abi(factory_name, is_classic=is_classic)
    instance = deploy_contract(provider, deployer, factory_name, is_classic=is_classic)
    proxy_factory = deploy_contract(provider, deployer, 'TransparentUpgradeableProxy', instance.address, admin.address, data_to_call_proxy, is_classic=is_classic)
    return provider.eth.contract(address=proxy_factory.address, abi=contract_abi)

def deploy_erc20_l1(provider, deployer):
    proxy_admin = deploy_contract(provider, deployer, 'ProxyAdmin', is_classic=False)
    print('proxy admin address', proxy_admin.address)
    router = deploy_behind_proxy(provider, deployer, 'L1GatewayRouter', proxy_admin, is_classic=True)
    print('router address', router.address)
    standard_gateway = deploy_behind_proxy(provider, deployer, 'L1ERC20Gateway', proxy_admin, is_classic=True)
    print('standard gateway address', standard_gateway.address)
    custom_gateway = deploy_behind_proxy(provider, deployer, 'L1CustomGateway', proxy_admin, is_classic=True)
    print('custom gateway address', custom_gateway.address)
    weth_gateway = deploy_behind_proxy(provider, deployer, 'L1WethGateway', proxy_admin, is_classic=True)
    print('weth gateway address', weth_gateway.address)
    weth = deploy_contract(provider, deployer, 'TestWETH9', 'WETH', 'WETH', is_classic=True)
    print('weth address', weth.address)
    multicall = deploy_contract(provider, deployer, 'Multicall2', is_classic=True)
    print('multicall address', multicall.address)

    return {
        'proxyAdmin': proxy_admin,
        'router': router,
        'standardGateway': standard_gateway,
        'customGateway': custom_gateway,
        'wethGateway': weth_gateway,
        'weth': weth,
        'multicall': multicall,
    }

def deploy_erc20_l2(provider, deployer):
    proxy_admin = deploy_contract(provider, deployer, 'ProxyAdmin', is_classic=False)
    print('proxy admin address', proxy_admin.address)
    router = deploy_behind_proxy(provider, deployer, 'L2GatewayRouter', proxy_admin, is_classic=True)
    print('router address', router.address)
    standard_gateway = deploy_behind_proxy(provider, deployer, 'L2ERC20Gateway', proxy_admin, is_classic=True)
    print('standard gateway address', standard_gateway.address)
    custom_gateway = deploy_behind_proxy(provider, deployer, 'L2CustomGateway', proxy_admin, is_classic=True)
    print('custom gateway address', custom_gateway.address)
    weth_gateway = deploy_behind_proxy(provider, deployer, 'L2WethGateway', proxy_admin, is_classic=True)
    print('weth gateway address', weth_gateway.address)

    standard_arb_erc20 = deploy_contract(provider, deployer, 'StandardArbERC20', is_classic=True)
    print('standard arb erc20 address', standard_arb_erc20.address)
    beacon = deploy_contract(provider, deployer, 'UpgradeableBeacon', standard_arb_erc20.address, is_classic=False)
    print('beacon address', beacon.address)
    beacon_proxy = deploy_contract(provider, deployer, 'BeaconProxyFactory', is_classic=True)
    print('beacon proxy address', beacon_proxy.address)

    weth = deploy_behind_proxy(provider, deployer, 'AeWETH', proxy_admin, is_classic=True)
    print('weth address', weth.address)
    multicall = deploy_contract(provider, deployer, 'ArbMulticall2', is_classic=True)
    print('multicall address', multicall.address)

    return {
        'proxyAdmin': proxy_admin,
        'router': router,
        'standardGateway': standard_gateway,
        'customGateway': custom_gateway,
        'wethGateway': weth_gateway,
        'beacon': beacon,
        'beaconProxyFactory': beacon_proxy,
        'weth': weth,
        'multicall': multicall,
    }


def sign_and_send_transaction(provider, contract_function, signer, nonce=None):
    # Build the transaction
    transaction = contract_function.build_transaction({
        'from': signer.address,
        'nonce': nonce if nonce is not None else provider.eth.get_transaction_count(signer.address),
        'gas': 2528712,  # Adjust as needed
        'gasPrice': provider.to_wei('21', 'gwei')
    })

    # Sign the transaction
    signed_txn = signer.sign_transaction(transaction)

    # Send the transaction
    tx_hash = provider.eth.send_raw_transaction(signed_txn.rawTransaction)
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt


def deploy_erc20_and_init(l1_provider, l1_signer, l2_provider, l2_signer, inbox_address: Address):
    print('Deploying L1 contracts...')
    l1_contracts = deploy_erc20_l1(l1_provider, l1_signer)

    print('Deploying L2 contracts...')
    l2_contracts = deploy_erc20_l2(l2_provider, l2_signer)

    print('Initializing L2 contracts...')
    sign_and_send_transaction(
        l2_provider,
        l2_contracts['router'].functions.initialize(
            l1_contracts['router'].address,
            l2_contracts['standardGateway'].address
        ),
        l2_signer
    )

    sign_and_send_transaction(
        l2_provider,
        l2_contracts['beaconProxyFactory'].functions.initialize(
            l2_contracts['beacon'].address
        ),
        l2_signer
    )

    sign_and_send_transaction(
        l2_provider,
        l2_contracts['standardGateway'].functions.initialize(
            l1_contracts['standardGateway'].address,
            l2_contracts['router'].address,
            l2_contracts['beaconProxyFactory'].address
        ),
        l2_signer
    )

    sign_and_send_transaction(
        l2_provider,
        l2_contracts['customGateway'].functions.initialize(
            l1_contracts['customGateway'].address,
            l2_contracts['router'].address
        ),
        l2_signer
    )

    sign_and_send_transaction(
        l2_provider,
        l2_contracts['weth'].functions.initialize(
            'WETH',
            'WETH',
            18,
            l2_contracts['wethGateway'].address,
            l1_contracts['weth'].address
        ),
        l2_signer
    )

    sign_and_send_transaction(
        l2_provider,
        l2_contracts['wethGateway'].functions.initialize(
            l1_contracts['wethGateway'].address,
            l2_contracts['router'].address,
            l1_contracts['weth'].address,
            l2_contracts['weth'].address
        ),
        l2_signer
    )

    print('Initializing L1 contracts...')
    sign_and_send_transaction(
        l1_provider,
        l1_contracts['router'].functions.initialize(
            l1_signer.address,
            l1_contracts['standardGateway'].address,
            ADDRESS_ZERO,  # Typically a zero address or specific address based on your setup
            l2_contracts['router'].address,
            inbox_address
        ),
        l1_signer
    )


    cloneable_proxy_hash = l2_provider.eth.contract(
        address=l2_contracts['beaconProxyFactory'].address,
        abi=l2_contracts['beaconProxyFactory'].abi
    ).functions.cloneableProxyHash().call()


    sign_and_send_transaction(
        l1_provider,
        l1_contracts['standardGateway'].functions.initialize(
            l2_contracts['standardGateway'].address,
            l1_contracts['router'].address,
            inbox_address,
            cloneable_proxy_hash,
            l2_contracts['beaconProxyFactory'].address
        ),
        l1_signer
    )

    sign_and_send_transaction(
        l1_provider,
        l1_contracts['customGateway'].functions.initialize(
            l2_contracts['customGateway'].address,
            l1_contracts['router'].address,
            inbox_address,
            l1_signer.address
        ),
        l1_signer
    )

    sign_and_send_transaction(
        l1_provider,
        l1_contracts['wethGateway'].functions.initialize(
            l2_contracts['wethGateway'].address,
            l1_contracts['router'].address,
            inbox_address,
            l1_contracts['weth'].address,
            l2_contracts['weth'].address
        ),
        l1_signer
    )

    return l1_contracts, l2_contracts

