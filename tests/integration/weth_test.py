from eth_account import Account
from web3 import Web3
import pytest
from scripts.test_setup import setup_testing_env
from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.utils.helper import load_contract
from tests.integration.test_helpers import (
    GatewayType,
    deposit_token,
    fund_child_signer,
    fund_parent_signer,
    withdraw_token,
)


def test_deposit_weth():
    """Test depositing WETH from parent to child chain"""
    setup_state = setup_testing_env()
    child_chain = setup_state.child_chain
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    erc20_bridger = setup_state.erc20_bridger

    parent_weth_address = child_chain.token_bridge.parent_weth

    weth_to_wrap = Web3.to_wei(0.00001, "ether")
    weth_to_deposit = Web3.to_wei(0.0000001, "ether")

    fund_parent_signer(parent_signer, Web3.to_wei(1, "ether"))

    child_WETH = load_contract(
        provider=child_signer.provider,
        address=child_chain.token_bridge.child_weth,
        contract_name="AeWETH",
    )
    assert (child_WETH.functions.balanceOf(child_signer.account.address).call()) == 0

    parent_WETH = load_contract(provider=parent_signer.provider, address=parent_weth_address, contract_name="AeWETH")

    tx = parent_WETH.functions.deposit().build_transaction(
        {
            "from": parent_signer.account.address,
            "value": weth_to_wrap,
            "nonce": parent_signer.provider.eth.get_transaction_count(parent_signer.account.address),
        }
    )
    signed_tx = parent_signer.account.sign_transaction(tx)
    tx_hash = parent_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    deposit_token(
        {
            "depositAmount": weth_to_deposit,
            "parentTokenAddress": parent_weth_address,
            "erc20Bridger": erc20_bridger,
            "parentSigner": parent_signer,
            "childSigner": child_signer,
            "expectedStatus": ParentToChildMessageStatus.REDEEMED,
            "expectedGatewayType": GatewayType.WETH,
        }
    )

    child_weth_gateway = erc20_bridger.get_child_gateway_address(parent_weth_address, child_signer.provider)
    assert child_weth_gateway == child_chain.token_bridge.child_weth_gateway

    child_token = erc20_bridger.get_child_token_contract(child_signer.provider, child_chain.token_bridge.child_weth)
    assert child_token.address == child_chain.token_bridge.child_weth

    fund_child_signer(child_signer)

    child_weth = load_contract(provider=child_signer.provider, address=child_token.address, contract_name="AeWETH")

    random_addr = Account.create().address
    tx = child_weth.functions.withdrawTo(random_addr, weth_to_deposit).build_transaction(
        {
            "from": child_signer.account.address,
            "nonce": child_signer.provider.eth.get_transaction_count(child_signer.account.address),
        }
    )
    signed_tx = child_signer.account.sign_transaction(tx)
    tx_hash = child_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    child_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
    after_balance = child_signer.provider.eth.get_balance(random_addr)
    assert str(after_balance) == str(weth_to_deposit)


def test_withdraw_weth():
    """Test withdrawing WETH from child to parent chain"""
    weth_to_wrap = Web3.to_wei(0.00001, "ether")
    weth_to_withdraw = Web3.to_wei(0.00000001, "ether")

    setup_state = setup_testing_env()
    child_chain = setup_state.child_chain
    parent_signer = setup_state.parent_signer
    child_signer = setup_state.child_signer
    erc20_bridger = setup_state.erc20_bridger

    fund_parent_signer(parent_signer)
    fund_child_signer(child_signer)

    child_weth = load_contract(
        provider=child_signer.provider,
        address=child_chain.token_bridge.child_weth,
        contract_name="AeWETH",
    )

    tx = child_weth.functions.deposit().build_transaction(
        {
            "from": child_signer.account.address,
            "value": weth_to_wrap,
            "nonce": child_signer.provider.eth.get_transaction_count(child_signer.account.address),
        }
    )
    signed_tx = child_signer.account.sign_transaction(tx)
    tx_hash = child_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    rec = child_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
    assert rec.status == 1, "deposit txn failed"

    withdraw_token(
        {
            "amount": weth_to_withdraw,
            "erc20Bridger": erc20_bridger,
            "gatewayType": GatewayType.WETH,
            "parentSigner": parent_signer,
            "parentToken": load_contract(
                provider=parent_signer.provider,
                address=child_chain.token_bridge.parent_weth,
                contract_name="ERC20",
            ),
            "childSigner": child_signer,
            "startBalance": weth_to_wrap,
        }
    )
