import os
import json
from web3 import Web3, HTTPProvider
import subprocess
from web3 import Web3, HTTPProvider
from web3 import Account
from web3.middleware import geth_poa_middleware
from yaml import Token
from pathlib import Path
from addict import Dict
from src.lib.data_entities.errors import ArbSdkError

from src.lib.utils.helper import CaseDict, load_contract
from src.lib.data_entities.networks import add_custom_network, get_l1_network, get_l2_network
from src.lib.asset_briger.erc20_bridger import AdminErc20Bridger, Erc20Bridger
from src.lib.asset_briger.eth_bridger import EthBridger
from src.lib.inbox.inbox import InboxTools
from src.scripts import PROJECT_DIRECTORY
from .deploy_bridge import deploy_erc20_and_init
from src.lib.data_entities.networks import L1Network, L2Network, EthBridge, TokenBridge

config = {
    'ARB_URL': os.getenv('ARB_URL'),
    'ETH_URL': os.getenv('ETH_URL'),
    'ARB_KEY': os.getenv('ARB_KEY'),
    'ETH_KEY': os.getenv('ETH_KEY'),
}

def get_deployment_data():
    docker_names = [
        # 'nitro_sequencer_1',
        # 'nitro-sequencer-1',
        # 'nitro-testnode-sequencer-1',
        'nitro-testnode-sequencer-1',
    ]
    for docker_name in docker_names:
        try:
            return subprocess.check_output(
                ['docker', 'exec', docker_name, 'cat', '/config/deployment.json']
            ).decode('utf-8')
        except Exception as e:
            # Handle exceptions as needed
            pass
    raise Exception('nitro-testnode sequencer not found')

def get_custom_networks(l1_url: str, l2_url: str):
    # Connect to the Ethereum and Arbitrum JSON-RPC endpoints
    l1_provider = Web3(Web3.HTTPProvider(l1_url))
    l2_provider = Web3(Web3.HTTPProvider(l2_url))

    # If the L1 or L2 network is a POA network, inject the middleware
    l1_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    l2_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Fetch the deployment data from the local Arbitrum node
    deployment_data = json.loads(get_deployment_data())

    # Extract the relevant addresses from the deployment data
    bridge_address = Web3.to_checksum_address(deployment_data['bridge'])
    inbox_address = Web3.to_checksum_address(deployment_data['inbox'])
    sequencer_inbox_address = Web3.to_checksum_address(deployment_data['sequencer-inbox'])
    rollup_address = Web3.to_checksum_address(deployment_data['rollup'])

    # Fetch additional configuration from the contracts (like confirmPeriodBlocks)
    rollup_contract = load_contract(l1_provider, 'RollupAdminLogic', rollup_address, is_classic=False)
    # rollup_contract = l1_provider.eth.contract(address=rollup_address, abi=RollupAdminLogicABI)  # Add RollupAdminLogicABI
    confirm_period_blocks = rollup_contract.functions.confirmPeriodBlocks().call()
    
    bridge_contract = load_contract(l1_provider, 'Bridge', bridge_address, is_classic=False)
    # bridge_contract = l1_provider.eth.contract(address=bridge_address, abi=BridgeABI)  # Add BridgeABI
    outbox_address = bridge_contract.functions.allowedOutboxList(0).call()

    l1_network_info = l1_provider.eth.chain_id
    l2_network_info = l2_provider.eth.chain_id

    l1_network = L1Network(
        blockTime = 10,
        chainID = int(l1_network_info),
        explorerUrl ='',
        isCustom= True,
        name='EthLocal',
        partnerChainIDs= [int(l2_network_info)],
        isArbitrum=False,
    )

    l2_network = L2Network(
        chainID =  int(l2_network_info),
        confirmPeriodBlocks = confirm_period_blocks,
        ethBridge = EthBridge(
            bridge = bridge_address,
            inbox = inbox_address,
            outbox = outbox_address,
            rollup = rollup_address,
            sequencerInbox = sequencer_inbox_address,
        ),
        tokenBridge= {},
        explorerUrl= '',
        isArbitrum= True,
        isCustom= True,
        name= 'ArbLocal',
        partnerChainID= int(l1_network_info),
        retryableLifetimeSeconds= 7 * 24 * 60 * 60,
        nitroGenesisBlock= 0,
        nitroGenesisL1Block= 0,
        depositTimeout= 900000
    )

    return {
        'l1Network': l1_network,
        'l2Network': l2_network,
    }

async def setup_networks(l1_url: str, l2_url: str, l1_deployer: Account, l2_deployer: Account, l1_provider: Web3, l2_provider: Web3):


    # Fetch the custom networks
    custom_networks = get_custom_networks(l1_url, l2_url)
    # Deploy necessary contracts and get their addresses
    l1_contracts, l2_contracts = deploy_erc20_and_init(
        l1_provider= l1_provider, l2_provider=l2_provider,
        l1_signer=l1_deployer, l2_signer=l2_deployer,
        inbox_address=custom_networks['l2Network']['ethBridge']['inbox']
    )

    # Add token bridge information to the L2 network
    l2_network = custom_networks['l2Network']
    l2_network.tokenBridge = TokenBridge(
        l1CustomGateway = l1_contracts['customGateway'],
        l1ERC20Gateway = l1_contracts['standardGateway'],
        l1GatewayRouter = l1_contracts['router'],
        l1MultiCall = l1_contracts['multicall'],
        l1ProxyAdmin = l1_contracts['proxyAdmin'],
        l1Weth = l1_contracts['weth'],
        l1WethGateway = l1_contracts['wethGateway'],
        l2CustomGateway = l2_contracts['customGateway'],
        l2ERC20Gateway = l2_contracts['standardGateway'],
        l2GatewayRouter = l2_contracts['router'],
        l2Multicall = l2_contracts['multicall'],
        l2ProxyAdmin = l2_contracts['proxyAdmin'],
        l2Weth = l2_contracts['weth'],
        l2WethGateway = l2_contracts['wethGateway'],
    )
    l1_network = custom_networks['l1Network']
    
    add_custom_network(l1_network, l2_network)
    
    # Register the WETH gateway and other necessary setups
    admin_erc20_bridger = AdminErc20Bridger(l2_network)
    await admin_erc20_bridger.set_gateways(
        l1_signer=l1_deployer,
        l1_provider=l1_provider,
        l2_signer=l2_deployer,
        l2_provider=l2_provider,
        token_gateways=[
            {
                'gatewayAddr': l2_network['tokenBridge']['l1WethGateway'],
                'tokenAddr': l2_network['tokenBridge']['l1Weth'],
            }
        ]
    )

    # Return the configured network and signers
    return {
        'l1Network': l1_network,
        'l2Network': l2_network,
        'l1Deployer': l1_deployer,
        'l2Deployer': l2_deployer,
    }

def get_signer(provider: Web3, key: str = None):
    if not key and not provider:
        raise Exception('Provide at least one of key or provider.')
    if key:
        account = Account.from_key(key)
        # Ensure that the provider is set to use this account for transactions
        provider.eth.default_account = Web3.to_checksum_address(account.address)
        return account
    else:
        # Assuming the first account is what you want to use
        # Adjust accordingly if you want to use a different account
        # return provider.eth.account.create()  # Or provider.eth.accounts[0] if accounts are already loaded
        return provider.eth.accounts[0]


async def test_setup() -> CaseDict:
    # Configure the Ethereum and Arbitrum providers
    eth_provider = Web3(HTTPProvider(config['ETH_URL']))
    arb_provider = Web3(HTTPProvider(config['ARB_URL']))

    # Adjust for PoA middleware if necessary
    eth_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    arb_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Create signers for deployments
    l1_deployer = get_signer(eth_provider, config['ETH_KEY'])
    l2_deployer = get_signer(arb_provider, config['ARB_KEY'])

    # Generate a new account for l1 and l2 signers
    seed = Account.create()
    l1_signer_address = Web3.to_checksum_address(seed.address)
    l2_signer_address = Web3.to_checksum_address(seed.address)
    print('l1_signer', l1_signer_address)
    print('l2_signer', l2_signer_address)
    print('l1_deployer', l1_deployer.address)
    print('l2_deployer', l2_deployer.address)


    # Set the default account for each provider to the new signer accounts
    eth_provider.eth.default_account = l1_signer_address
    arb_provider.eth.default_account = l2_signer_address
    signer_private_key = seed.key.hex()  


    signer_account = Account.from_key(signer_private_key)

   # Try to get the network configurations
    try:
        set_l1_network = get_l1_network(eth_provider)
        set_l2_network = get_l2_network(arb_provider)
    
    except ArbSdkError:
        # Handle the case where the networks haven't been added yet
        local_network_file = PROJECT_DIRECTORY / 'localNetwork.json'
        print(local_network_file.exists())
        if local_network_file.exists():
            with open(local_network_file, 'r') as file:
                network_data = json.load(file)
            set_l1_network = L1Network(**network_data['l1Network'])

            network_data['l2Network']['tokenBridge'] = TokenBridge(**network_data['l2Network']['tokenBridge'])
            network_data['l2Network']['ethBridge'] = EthBridge(**network_data['l2Network']['ethBridge'])
            set_l2_network = L2Network(**network_data['l2Network'])
            add_custom_network(set_l1_network, set_l2_network)            
        else:
            # Deploy a new network
            network_data = await setup_networks(
                l1_deployer=l1_deployer, l2_deployer=l2_deployer, l1_url= config['ETH_URL'], l2_url=config['ARB_URL'], l1_provider=eth_provider, l2_provider=arb_provider
            )
            set_l1_network = network_data['l1Network']
            set_l2_network = network_data['l2Network']

    # Initialize bridger and tools objects
    erc20_bridger = Erc20Bridger(set_l2_network)
    admin_erc20_bridger = AdminErc20Bridger(set_l2_network)
    eth_bridger = EthBridger(set_l2_network)
    inbox_tools = InboxTools(l1_signer_address, set_l2_network)

    return CaseDict({
        'l1_signer': l1_signer_address,
        'l2_signer': l2_signer_address,
        'l1_network': set_l1_network,
        'l2_network': set_l2_network,
        'erc20_bridger': erc20_bridger,
        'admin_erc20_bridger': admin_erc20_bridger,
        'eth_bridger': eth_bridger,
        'inbox_tools': inbox_tools,
        'l1_deployer': l1_deployer,
        'l2_deployer': l2_deployer,
        'l1_provider': eth_provider,
        'l2_provider': arb_provider,
        # 'l1_signer_private_key': signer_private_key,
        # 'l2_signer_private_key': signer_private_key,
        # 'l1_deployer_private_key': config['ETH_KEY'],
        # 'l2_deployer_private_key': config['ARB_KEY'],
        'l1_signer_account': signer_account,
        'l2_signer_account': signer_account,
    })