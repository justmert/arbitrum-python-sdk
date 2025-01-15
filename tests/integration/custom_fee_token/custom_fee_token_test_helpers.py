from typing import Union

from eth_account import Account
from eth_utils import keccak, to_bytes
from web3 import Web3

from scripts.setup_common import config, get_local_networks_from_file
from arbitrum_py.asset_bridger.erc20_bridger import Erc20Bridger
from arbitrum_py.asset_bridger.eth_bridger import EthBridger
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider
from arbitrum_py.utils.helper import load_contract
from arbitrum_py.utils.lib import get_native_token_decimals


def eth_provider():
    """Get Ethereum provider"""
    return Web3(Web3.HTTPProvider(config["ethUrl"]))


def arb_provider():
    """Get Arbitrum provider"""
    return Web3(Web3.HTTPProvider(config["arbUrl"]))


def local_networks():
    """Get local network configurations"""
    return get_local_networks_from_file()


def is_arbitrum_network_with_custom_fee_token() -> bool:
    """Check if network uses custom fee token"""
    l3_network = local_networks().get("l3Network")
    if not l3_network:
        return False
    native_token = l3_network.get("nativeToken")
    return native_token is not None and native_token != "0x" + "0" * 40


def test_setup():
    """Extended test setup with native token contract"""
    from scripts.test_setup import setup_testing_env as _test_setup  # Deferred import

    result = _test_setup()
    child_chain = result["childChain"]
    parent_provider = result["parentProvider"]

    native_token = child_chain.native_token
    if native_token:
        native_token_contract = load_contract(
            provider=parent_provider,
            contract_name="ERC20",
            address=native_token,
        )
        result["nativeTokenContract"] = native_token_contract

    return result


def fund_parent_custom_fee_token(parent_signer_or_address: Union[SignerOrProvider, str]) -> None:
    """Fund parent chain account with custom fee tokens"""
    native_token = local_networks().get("l3Network", {}).get("nativeToken")

    if not native_token:
        raise ValueError("Can't call 'fund_parent_custom_fee_token' for network that uses eth as native token")

    address = (
        parent_signer_or_address
        if isinstance(parent_signer_or_address, str)
        else parent_signer_or_address.account.address
    )

    # Create deterministic deployer wallet
    deployer_key = keccak(to_bytes(text="user_fee_token_deployer"))
    deployer_account = Account.from_key(deployer_key)
    deployer = SignerOrProvider(deployer_account, eth_provider())

    token_contract = load_contract(
        provider=deployer.provider,
        contract_name="ERC20",
        address=native_token,
    )

    decimals = token_contract.functions.decimals().call()
    amount = Web3.to_wei(10, decimals)  # 10 tokens with proper decimals

    tx = {
        "from": deployer.account.address,
        "to": native_token,
        "data": token_contract.encodeABI(fn_name="transfer", args=[address, amount]),
        "gas": 100000,
        "gasPrice": deployer.provider.eth.gas_price,
        "nonce": deployer.provider.eth.get_transaction_count(deployer.account.address),
    }

    signed_tx = deployer.account.sign_transaction(tx)
    tx_hash = deployer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    deployer.provider.eth.wait_for_transaction_receipt(tx_hash)


def approve_parent_custom_fee_token(parent_signer: SignerOrProvider):
    """Approve custom fee token spending"""
    eth_bridger = EthBridger.from_provider(arb_provider())
    tx = eth_bridger.approve_gas_token({"parentSigner": parent_signer})
    tx.wait()


def get_parent_custom_fee_token_allowance(owner: str, spender: str):
    """Get token allowance for owner->spender"""
    native_token = local_networks().get("l3Network", {}).get("nativeToken")
    native_token_contract = load_contract(
        provider=eth_provider(),
        contract_name="ERC20",
        address=native_token,
    )
    return native_token_contract.functions.allowance(owner, spender).call()


def approve_parent_custom_fee_token_for_erc20_deposit(parent_signer: SignerOrProvider, erc20_parent_address: str):
    """Approve custom fee token for ERC20 deposit"""
    erc20_bridger = Erc20Bridger.from_provider(arb_provider())
    tx = erc20_bridger.approve_gas_token({"erc20ParentAddress": erc20_parent_address, "parentSigner": parent_signer})
    tx.wait()


def fund_child_custom_fee_token(child_signer: SignerOrProvider):
    """Fund child chain account with custom fee tokens"""
    deployer_account = Account.from_key(config["arbKey"])
    deployer = SignerOrProvider(deployer_account, arb_provider())

    decimals = get_native_token_decimals(parent_provider=eth_provider(), child_network=local_networks()["l2Network"])

    tx = {
        "from": deployer.account.address,
        "to": child_signer.account.address,
        "value": Web3.to_wei(1, decimals),
        "gas": 21000,
        "gasPrice": deployer.provider.eth.gas_price,
        "nonce": deployer.provider.eth.get_transaction_count(deployer.account.address),
    }

    signed_tx = deployer.account.sign_transaction(tx)
    tx_hash = deployer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    deployer.provider.eth.wait_for_transaction_receipt(tx_hash)
