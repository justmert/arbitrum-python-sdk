from src.lib.utils.helper import load_contract, sign_and_sent_raw_transaction
from .test_helpers import fund_l1, fund_l2, withdraw_token, skip_if_mainnet, deposit_token, GatewayType, withdraw_token
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from src.scripts.test_setup import test_setup
from eth_account import Account
from web3 import Web3
import pytest

# from your_project.lib.abi.factories import AeWETH__factory, ERC20__factory


# Helper function to parse Ether values
def parse_ether(value):
    return Web3.to_wei(value, "ether")


@pytest.mark.asyncio
async def test_deposit_weth():
    setup_state = await test_setup()
    l2_network = setup_state.l2_network
    l1_signer = setup_state.l1_signer
    l2_signer = setup_state.l2_signer
    erc20_bridger = setup_state.erc20_bridger

    l1_weth_address = l2_network.token_bridge.l1_weth

    weth_to_wrap = parse_ether("0.00001")
    weth_to_deposit = parse_ether("0.0000001")

    fund_l1(l1_signer, parse_ether("1"))

    # l2_weth = AeWETH__factory.connect(l2_network.token_bridge.l2_weth, l2_signer.provider)

    l2_WETH = load_contract(
        provider=l2_signer.provider, address=l2_network.token_bridge.l2_weth, contract_name="AeWETH", is_classic=True
    )
    # x = l2_WETH.functions.balanceOf(l2_signer.account.address).call()
    assert (l2_WETH.functions.balanceOf(l2_signer.account.address).call()) == 0

    # l1_weth = AeWETH__factory.connect(l1_weth_address, l1_signer)
    l1_WETH = load_contract(
        provider=l1_signer.provider, address=l1_weth_address, contract_name="AeWETH", is_classic=True
    )

    tx = l1_WETH.functions.deposit().build_transaction({"value": weth_to_wrap})

    sign_and_sent_raw_transaction(l1_signer, tx)

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

    # l2_weth = AeWETH__factory.connect(l2_token.address, l2_signer)
    random_addr = Account.create().address
    tx = l2_weth.functions.withdrawTo(random_addr, weth_to_deposit).build_transaction()
    sign_and_sent_raw_transaction(l2_signer, tx)

    after_balance = await l2_signer.provider.getBalance(random_addr)

    assert after_balance.toString() == weth_to_deposit.toString()


# @pytest.mark.asyncio
# async def test_withdraw_weth():
#     weth_to_wrap = parse_ether('0.00001')
#     weth_to_withdraw = parse_ether('0.00000001')

#     setup_state = await test_setup()
#     fund_l1(setup_state.l1_signer)
#     fund_l2(setup_state.l2_signer)

#     l2_weth = AeWETH__factory.connect(setup_state.l2_network.token_bridge.l2_weth, setup_state.l2_signer)
#     res = await l2_weth.deposit({'value': weth_to_wrap})
#     rec = await res.wait()
#     assert rec.status == 1

#     await withdraw_token({
#         'amount': weth_to_withdraw,
#         'erc20_bridger': setup_state.erc20_bridger,
#         'gateway_type': GatewayType.WETH,
#         'l1_signer': setup_state.l1_signer,
#         'l1_token': ERC20__factory.connect(setup_state.l2_network.token_bridge.l1_weth, setup_state.l1_signer.provider),
#         'l2_signer': setup_state.l2_signer,
#         'start_balance': weth_to_wrap
#     })
