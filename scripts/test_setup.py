import json
import os
from pathlib import Path
from typing import Dict, Optional
from web3 import Account, HTTPProvider, Web3
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

from arbitrum_py.asset_bridger.erc20_bridger import AdminErc20Bridger, Erc20Bridger
from arbitrum_py.asset_bridger.eth_bridger import EthBridger
from arbitrum_py.data_entities.errors import ArbSdkError

from arbitrum_py.data_entities.networks import (
    assert_arbitrum_network_has_token_bridge,
    get_arbitrum_network,
    register_custom_arbitrum_network,
)
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider
from arbitrum_py.inbox.inbox import InboxTools
from arbitrum_py.utils.helper import CaseDict
from tests.integration.test_helpers import fund_parent_signer
import pytest

# Import shared config and utility functions
from scripts.setup_common import (
    config,
    get_local_networks_from_file,
    IS_TESTING_ORBIT_CHAINS,
    get_signer,
)

# Import custom fee token helper functions without causing circular import
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    approve_parent_custom_fee_token,
    fund_parent_custom_fee_token,
    is_arbitrum_network_with_custom_fee_token,
)


def setup_testing_env():
    """Setup test environment with bridgers and networks"""
    eth_provider = Web3(HTTPProvider(config["ethUrl"]))
    arb_provider = Web3(HTTPProvider(config["arbUrl"]))

    eth_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    arb_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    parent_deployer = SignerOrProvider(get_signer(eth_provider, config["ethKey"]), eth_provider)
    child_deployer = SignerOrProvider(get_signer(arb_provider, config["arbKey"]), arb_provider)

    seed = Account.create()
    signer_private_key = seed.key.hex()
    signer_account = Account.from_key(signer_private_key)

    eth_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(signer_account))

    arb_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(signer_account))

    # Add signing middleware
    eth_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(config["ethKey"]))
    arb_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(config["arbKey"]))

    parent_signer = SignerOrProvider(signer_account, eth_provider)
    child_signer = SignerOrProvider(signer_account, arb_provider)

    try:
        set_child_chain = get_arbitrum_network(child_deployer)
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
        fund_parent_signer(parent_signer)
        fund_parent_custom_fee_token(parent_signer)
        approve_parent_custom_fee_token(parent_signer)

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
