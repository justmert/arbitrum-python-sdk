from web3 import Web3
from web3.contract import Contract
from eth_typing import Address
from src.lib.utils.helper import load_contract
from web3.eth import Account
import json

def load_contract_abi(name: str) -> list:
    with open(f'src/abi/{name}.json', 'r') as abi_file:
        contract_data = json.load(abi_file)
        if not contract_data.get('abi'):
            raise Exception(f'No ABI found for contract: {name}')
        if not contract_data.get('bytecode'):
            raise Exception(f'No bytecode found for contract: {name}')
        return contract_data['abi'], contract_data['bytecode']


def deploy_contract(provider: Web3, deployer: Account, contract_name: str, *constructor_args) -> str:
    # Load contract ABI
    contract_abi, bytecode = load_contract_abi(contract_name)
        
    # Create contract factory
    contract_factory = provider.eth.contract(abi=contract_abi, bytecode=bytecode)

    # Build constructor transaction
    construct_txn = contract_factory.constructor(*constructor_args).buildTransaction({
        'from': deployer.address,
        'nonce': provider.eth.getTransactionCount(deployer.address),
        'gas': 1728712,  # You might want to estimate this value
        'gasPrice': provider.toWei('21', 'gwei')
    })

    # Sign transaction with deployer account
    signed = deployer.signTransaction(construct_txn)

    # Send transaction
    tx_hash = provider.eth.sendRawTransaction(signed.rawTransaction)

    # Wait for transaction receipt to confirm deployment
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)

    # Return contract address
    return tx_receipt.contractAddress


def deploy_behind_proxy(provider, deployer: Account, factory_name: str, admin: Contract, data_to_call_proxy='0x') -> Contract:
    factory = load_contract_abi(provider, factory_name, '')
    instance = factory.constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(instance)

    proxy_factory = load_contract_abi(provider, 'TransparentUpgradeableProxy.json', '')
    proxy = proxy_factory.constructor(instance, admin.address, data_to_call_proxy).transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(proxy)

    print(factory_name, proxy)
    return provider.eth.contract(address=proxy, abi=factory.abi)


def deploy_erc20_l1(provider, deployer):
    proxy_admin_factory = load_contract_abi(provider, 'ProxyAdmin', '')
    print(proxy_admin_factory)
    proxy_admin = proxy_admin_factory.constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(proxy_admin)

    print('proxyAdmin', proxy_admin)

    router = deploy_behind_proxy(provider, deployer, 'L1GatewayRouter.json', proxy_admin)
    standard_gateway = deploy_behind_proxy(provider, deployer, 'L1ERC20Gateway.json', proxy_admin)
    custom_gateway = deploy_behind_proxy(provider, deployer, 'L1CustomGateway.json', proxy_admin)
    weth_gateway = deploy_behind_proxy(provider, deployer, 'L1WethGateway.json', proxy_admin)

    test_weth_factory = load_contract_abi(provider, 'TestWETH9.json', '')
    weth = test_weth_factory.constructor('WETH', 'WETH').transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(weth)

    print('weth', weth)

    multicall_factory = load_contract_abi(provider, 'Multicall2.json', '')
    multicall = multicall_factory.constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(multicall)

    print('multicall', multicall)

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
    proxy_admin = deploy_contract(provider, deployer, 'ProxyAdmin')
    print('proxyAdmin', proxy_admin)


    router = deploy_behind_proxy(provider, deployer, 'L2GatewayRouter.json', proxy_admin)
    standard_gateway = deploy_behind_proxy(provider, deployer, 'L2ERC20Gateway.json', proxy_admin)
    custom_gateway = deploy_behind_proxy(provider, deployer, 'L2CustomGateway.json', proxy_admin)
    weth_gateway = deploy_behind_proxy(provider, deployer, 'L2WethGateway.json', proxy_admin)

    standard_arb_erc20_factory = load_contract_abi(provider, 'StandardArbERC20.json', '')
    standard_arb_erc20 = standard_arb_erc20_factory.constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(standard_arb_erc20)

    beacon_factory = load_contract_abi(provider, 'UpgradeableBeacon.json', '')
    beacon = beacon_factory.constructor(standard_arb_erc20).transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(beacon)

    beacon_proxy_factory = load_contract_abi(provider, 'BeaconProxyFactory.json', '')
    beacon_proxy = beacon_proxy_factory.constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(beacon_proxy)

    weth = deploy_behind_proxy(provider, deployer, 'AeWETH.json', proxy_admin)
    multicall = load_contract_abi(provider, 'ArbMulticall2.json', '').constructor().transact({'from': deployer.address})
    provider.eth.wait_for_transaction_receipt(multicall)

    print('multicall', multicall)

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


def deploy_erc20_and_init(l1_provider, l1_signer, l2_provider, l2_signer, inbox_address: Address):
    print('deploying l1')
    # l1 = deploy_erc20_l1(l1_provider, l1_signer)

    print('deploying l2')
    l2 = deploy_erc20_l2(l2_provider, l2_signer)

    print('initialising L2')
    l2['router'].functions.initialize(l1['router'].address, l2['standardGateway'].address).transact({'from': l2_signer.eth.defaultAccount})
    l2['beaconProxyFactory'].functions.initialize(l2['beacon'].address).transact({'from': l2_signer.eth.defaultAccount})
    l2['standardGateway'].functions.initialize(
        l1['standardGateway'].address,
        l2['router'].address,
        l2['beaconProxyFactory'].address
    ).transact({'from': l2_signer.eth.defaultAccount})
    l2['customGateway'].functions.initialize(
        l1['customGateway'].address,
        l2['router'].address
    ).transact({'from': l2_signer.eth.defaultAccount})
    l2['weth'].functions.initialize(
        'WETH',
        'WETH',
        18,
        l2['wethGateway'].address,
        l1['weth'].address
    ).transact({'from': l2_signer.eth.defaultAccount})
    l2['wethGateway'].functions.initialize(
        l1['wethGateway'].address,
        l2['router'].address,
        l1['weth'].address,
        l2['weth'].address
    ).transact({'from': l2_signer.eth.defaultAccount})

    print('initialising L1')
    l1['router'].functions.initialize(
        l1_signer.eth.defaultAccount,
        l1['standardGateway'].address,
        inbox_address,
        l2['router'].address
    ).transact({'from': l1_signer.eth.defaultAccount})
    l1['standardGateway'].functions.initialize(
        l2['standardGateway'].address,
        l1['router'].address,
        inbox_address,
        l2['beaconProxyFactory'].address
    ).transact({'from': l1_signer.eth.defaultAccount})
    l1['customGateway'].functions.initialize(
        l2['customGateway'].address,
        l1['router'].address,
        inbox_address
    ).transact({'from': l1_signer.eth.defaultAccount})
    l1['wethGateway'].functions.initialize(
        l2['wethGateway'].address,
        l1['router'].address,
        inbox_address,
        l1['weth'].address,
        l2['weth'].address
    ).transact({'from': l1_signer.eth.defaultAccount})

    return {'l1': l1, 'l2': l2}