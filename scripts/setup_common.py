# src/lib/data_entities/setup_common.py

import json
import os
from pathlib import Path
from typing import Dict, Optional

from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.utils.helper import CaseDict

from typing import Dict, Optional

from web3 import Account, HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from arbitrum_py.asset_bridger.erc20_bridger import AdminErc20Bridger, Erc20Bridger
from arbitrum_py.asset_bridger.eth_bridger import EthBridger
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider, SignerProviderUtils


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


def get_local_networks_from_file() -> Dict:
    """Read networks configuration from local file"""
    network_path = Path(__file__).parent.parent / "localNetwork.json"

    if not network_path.exists():
        raise ArbSdkError("localNetwork.json not found, must gen network first")

    with open(network_path) as f:
        networks = json.load(f)

    return {"l2Network": networks["l2Network"], "l3Network": networks.get("l3Network")}


def get_signer(provider: Web3, key: Optional[str] = None) -> SignerOrProvider:
    """Get a signer either from a private key or provider's first account"""
    if not key and not provider:
        raise ArbSdkError("Provide at least one of key or provider.")
    if key:
        account = Account.from_key(key)
        return account
    else:
        return SignerProviderUtils.get_provider_or_throw(provider).eth.accounts[0]
