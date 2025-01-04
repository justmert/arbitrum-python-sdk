import json
import os
from pathlib import Path
from typing import Dict, Optional

from web3 import Account, HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from src.lib.asset_bridger.erc20_bridger import AdminErc20Bridger, Erc20Bridger
from src.lib.asset_bridger.eth_bridger import EthBridger
from src.lib.data_entities.errors import ArbSdkError

from src.lib.data_entities.networks import (
    assert_arbitrum_network_has_token_bridge,
    get_arbitrum_network,
    register_custom_arbitrum_network,
)
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.inbox.inbox import InboxTools
from src.lib.utils.helper import CaseDict
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    approve_parent_custom_fee_token,
    fund_parent_custom_fee_token,
    is_arbitrum_network_with_custom_fee_token,
)

from tests.integration.test_helpers import fund_parent_signer

IS_TESTING_ORBIT_CHAINS = os.getenv("ORBIT_TEST") == "1"

# Configuration dict taking into account Orbit testing
if IS_TESTING_ORBIT_CHAINS:
    config = {
        "arbUrl": os.getenv("ORBIT_URL"),
        "ethUrl": os.getenv("ARB_URL"),
        "arbKey": os.getenv("ORBIT_KEY"),
        "ethKey": os.getenv("ARB_KEY"),
    }
else:
    config = {
        "arbUrl": os.getenv("ARB_URL"),
        "ethUrl": os.getenv("ETH_URL"),
        "arbKey": os.getenv("ARB_KEY"),
        "ethKey": os.getenv("ETH_KEY"),
    }


def get_signer(provider: Web3, key: Optional[str] = None) -> SignerOrProvider:
    """Get a signer either from a private key or provider's first account"""
    if not key and not provider:
        raise ArbSdkError("Provide at least one of key or provider.")
    if key:
        account = Account.from_key(key)
        return SignerOrProvider(account, provider)
    else:
        return SignerOrProvider(provider.eth.accounts[0], provider)


def get_local_networks_from_file() -> Dict:
    """Read networks configuration from local file"""
    network_path = Path(__file__).parent.parent / "localNetwork.json"
    if not network_path.exists():
        raise ArbSdkError("localNetwork.json not found, must gen:network first")

    with open(network_path) as f:
        networks = json.load(f)

    return {"l2Network": networks["l2Network"], "l3Network": networks.get("l3Network")}


async def test_setup():
    """Setup test environment with bridgers and networks"""
    eth_provider = Web3(HTTPProvider(config["ethUrl"]))
    arb_provider = Web3(HTTPProvider(config["arbUrl"]))

    eth_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    arb_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    parent_deployer = get_signer(eth_provider, config["ethKey"])
    child_deployer = get_signer(arb_provider, config["arbKey"])

    # Create random account for testing
    seed = Account.create()
    parent_signer = SignerOrProvider(seed, eth_provider)
    child_signer = SignerOrProvider(seed, arb_provider)

    try:
        set_child_chain = await get_arbitrum_network(child_deployer)
    except ArbSdkError:
        local_networks = get_local_networks_from_file()
        child_chain = local_networks["l3Network"] if IS_TESTING_ORBIT_CHAINS else local_networks["l2Network"]
        set_child_chain = register_custom_arbitrum_network(child_chain)

    assert_arbitrum_network_has_token_bridge(set_child_chain)

    # Initialize bridgers
    erc20_bridger = Erc20Bridger(set_child_chain)
    admin_erc20_bridger = AdminErc20Bridger(set_child_chain)
    eth_bridger = EthBridger(set_child_chain)
    inbox_tools = InboxTools(parent_signer, set_child_chain)

    # Handle custom fee token setup if needed
    if is_arbitrum_network_with_custom_fee_token():
        await fund_parent_signer(parent_signer)
        await fund_parent_custom_fee_token(parent_signer)
        await approve_parent_custom_fee_token(parent_signer)

    return CaseDict(
        {
            "parentSigner": parent_signer,
            "childSigner": child_signer,
            "parentProvider": eth_provider,
            "childProvider": arb_provider,
            "childChain": set_child_chain,
            "erc20Bridger": erc20_bridger,
            "adminErc20Bridger": admin_erc20_bridger,
            "ethBridger": eth_bridger,
            "inboxTools": inbox_tools,
            "parentDeployer": parent_deployer,
            "childDeployer": child_deployer,
        }
    )
