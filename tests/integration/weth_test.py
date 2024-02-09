import pytest
from eth_account import Account
from web3 import Web3

from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.lib.utils.helper import load_contract
from src.scripts.test_setup import test_setup
from tests.integration.test_helpers import (
    GatewayType,
    deposit_token,
    fund_l1,
    fund_l2,
    withdraw_token,
)


@pytest.mark.asyncio
async def test_deposit_weth():
    setup_state = await test_setup()
    l2_network = setup_state.l2_network
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    erc20_bridger = setup_state.erc20_bridger

    l1_weth_address = l2_network.token_bridge.l1_weth

    weth_to_wrap = Web3.to_wei(0.00001, "ether")
    weth_to_deposit = Web3.to_wei(0.0000001, "ether")

    fund_l1(l1_signer, Web3.to_wei(1, "ether"))

    l2_WETH = load_contract(
        provider=l2_signer.provider, address=l2_network.token_bridge.l2_weth, contract_name="AeWETH", is_classic=True
    )
    assert (l2_WETH.functions.balanceOf(l2_signer.account.address).call()) == 0

    l1_WETH = load_contract(
        provider=l1_signer.provider, address=l1_weth_address, contract_name="AeWETH", is_classic=True
    )

    tx = l1_WETH.functions.deposit().transact({"from": l1_signer.account.address, "value": weth_to_wrap})

    l1_signer.provider.eth.wait_for_transaction_receipt(tx)

    await deposit_token(
        weth_to_deposit,
        l1_weth_address,
        erc20_bridger,
        l1_signer,
        l2_signer,
        L1ToL2MessageStatus.REDEEMED,
        GatewayType.WETH,
    )

    l2_weth_gateway = await erc20_bridger.get_l2_gateway_address(l1_weth_address, l2_signer.provider)
    assert l2_weth_gateway == l2_network.token_bridge.l2_weth_gateway

    l2_token = erc20_bridger.get_l2_token_contract(l2_signer.provider, l2_network.token_bridge.l2_weth)
    assert l2_token.address == l2_network.token_bridge.l2_weth

    fund_l2(l2_signer)

    l2_weth = load_contract(
        provider=l2_signer.provider, address=l2_token.address, contract_name="AeWETH", is_classic=True
    )

    random_addr = Account.create().address
    tx = l2_weth.functions.withdrawTo(random_addr, weth_to_deposit).transact({"from": l2_signer.account.address})

    l2_signer.provider.eth.wait_for_transaction_receipt(tx)

    after_balance = l2_signer.provider.eth.get_balance(random_addr)

    assert str(after_balance) == str(weth_to_deposit)


@pytest.mark.asyncio
async def test_withdraw_weth():
    weth_to_wrap = Web3.to_wei(0.00001, "ether")
    weth_to_withdraw = Web3.to_wei(0.00000001, "ether")

    setup_state = await test_setup()
    l2_network = setup_state.l2_network
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    erc20_bridger = setup_state.erc20_bridger

    fund_l1(l1_signer)
    fund_l2(l2_signer)

    l2_weth = load_contract(
        provider=l2_signer.provider, address=l2_network.token_bridge.l2_weth, contract_name="AeWETH", is_classic=True
    )

    tx = l2_weth.functions.deposit().transact({"from": l2_signer.account.address, "value": weth_to_wrap})

    rec = l2_signer.provider.eth.wait_for_transaction_receipt(tx)

    assert rec.status == 1

    await withdraw_token(
        {
            "amount": weth_to_withdraw,
            "erc20Bridger": erc20_bridger,
            "gatewayType": GatewayType.WETH,
            "l1Signer": l1_signer,
            "l1Token": load_contract(
                provider=l1_signer.provider,
                address=l2_network.token_bridge.l1_weth,
                contract_name="ERC20",
                is_classic=True,
            ),
            "l2Signer": setup_state.l2_signer,
            "startBalance": weth_to_wrap,
        }
    )
