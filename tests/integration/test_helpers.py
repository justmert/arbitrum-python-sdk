import asyncio
import time

from web3 import Account, Web3

from src.lib.asset_briger.erc20_bridger import Erc20Bridger
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import L2ToL1MessageStatus
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.scripts.test_setup import config, get_signer

PRE_FUND_AMOUNT = Web3.to_wei(0.1, "ether")
arb_sys = "0x0000000000000000000000000000000000000064"


class GatewayType:
    STANDARD = 1
    CUSTOM = 2
    WETH = 3


async def mine_until_stop(miner, state):
    while state["mining"]:
        tx = {
            "from": miner.account.address,
            "to": miner.account.address,
            "value": 0,
            "chainId": miner.provider.eth.chain_id,
            "gasPrice": miner.provider.eth.gas_price,
            "nonce": miner.provider.eth.get_transaction_count(miner.account.address),
        }

        gas_estimate = miner.provider.eth.estimate_gas(tx)

        tx["gas"] = gas_estimate

        signed_tx = miner.account.sign_transaction(tx)

        tx_hash = miner.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        miner.provider.eth.wait_for_transaction_receipt(tx_hash)

        await asyncio.sleep(15)


async def withdraw_token(params):
    withdrawal_params = await params["erc20Bridger"].get_withdrawal_request(
        {
            "amount": params["amount"],
            "erc20L1Address": params["l1Token"].address,
            "destinationAddress": params["l2Signer"].account.address,
            "from": params["l2Signer"].account.address,
            "l2Provider": params["l2Signer"].provider,
        }
    )

    l1_gas_estimate = await withdrawal_params["estimateL1GasLimit"](params["l1Signer"].provider)

    withdraw_rec = await params["erc20Bridger"].withdraw(
        {
            "destinationAddress": params["l2Signer"].account.address,
            "amount": params["amount"],
            "erc20L1Address": params["l1Token"].address,
            "l2Signer": params["l2Signer"],
        }
    )

    assert withdraw_rec["status"] == 1, "initiate token withdraw txn failed"

    message = (await withdraw_rec.get_l2_to_l1_messages(params["l1Signer"]))[0]
    assert message is not None, "withdraw message not found"

    message_status = await message.status(params["l2Signer"].provider)
    assert message_status == L2ToL1MessageStatus.UNCONFIRMED, "invalid withdraw status"

    l2_token_addr = await params["erc20Bridger"].get_l2_erc20_address(
        params["l1Token"].address, params["l1Signer"].provider
    )
    l2_token = params["erc20Bridger"].get_l2_token_contract(params["l2Signer"].provider, l2_token_addr)

    test_wallet_l2_balance = l2_token.functions.balanceOf(params["l2Signer"].account.address).call()

    assert test_wallet_l2_balance == params["startBalance"] - params["amount"], "token withdraw balance not deducted"

    wallet_address = params["l1Signer"].account.address

    gateway_address = await params["erc20Bridger"].get_l2_gateway_address(
        params["l1Token"].address, params["l2Signer"].provider
    )

    expected_l2_gateway = get_gateways(params["gatewayType"], params["erc20Bridger"].l2_network)["expectedL2Gateway"]
    assert gateway_address == expected_l2_gateway, "Gateway is not custom gateway"

    gateway_withdraw_events = await params["erc20Bridger"].get_l2_withdrawal_events(
        params["l2Signer"].provider,
        gateway_address,
        {"fromBlock": withdraw_rec["blockNumber"], "toBlock": "latest"},
        params["l1Token"].address,
        wallet_address,
    )
    assert len(gateway_withdraw_events) == 1, "token query failed"

    bal_before = params["l1Token"].functions.balanceOf(params["l1Signer"].account.address).call()

    miner1_seed = Account.create()
    miner2_seed = Account.create()

    miner1_private_key = miner1_seed.key.hex()
    miner2_private_key = miner2_seed.key.hex()

    miner1_account = Account.from_key(miner1_private_key)
    miner2_account = Account.from_key(miner2_private_key)

    miner1 = SignerOrProvider(miner1_account, params["l1Signer"].provider)
    miner2 = SignerOrProvider(miner2_account, params["l2Signer"].provider)

    fund_l1(miner1, Web3.to_wei(1, "ether"))
    fund_l2(miner2, Web3.to_wei(1, "ether"))
    state = {"mining": True}

    tasks = [
        mine_until_stop(miner1, state),
        mine_until_stop(miner2, state),
        message.wait_until_ready_to_execute(params["l2Signer"].provider),
    ]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    state["mining"] = False

    assert await message.status(params["l2Signer"].provider) == L2ToL1MessageStatus.CONFIRMED, "confirmed status"

    exec_rec = await message.execute(params["l2Signer"].provider)

    assert exec_rec["gasUsed"] <= l1_gas_estimate, "Gas used greater than estimate"
    assert await message.status(params["l2Signer"].provider) == L2ToL1MessageStatus.EXECUTED, "executed status"

    bal_after = params["l1Token"].functions.balanceOf(params["l1Signer"].account.address).call()
    assert bal_before + params["amount"] == bal_after, "Not withdrawn"

    # Cancel all pending tasks
    for task in pending:
        task.cancel()
        # Optionally, you can try to await task to let it handle the cancellation
        try:
            await task
        except asyncio.CancelledError:
            pass  # Task cancellation is expected, handle it if necessary


def get_gateways(gateway_type, l2_network):
    if gateway_type == GatewayType.CUSTOM:
        return {
            "expectedL1Gateway": l2_network.token_bridge.l1_custom_gateway,
            "expectedL2Gateway": l2_network.token_bridge.l2_custom_gateway,
        }
    elif gateway_type == GatewayType.STANDARD:
        return {
            "expectedL1Gateway": l2_network.token_bridge.l1_erc20_gateway,
            "expectedL2Gateway": l2_network.token_bridge.l2_erc20_gateway,
        }
    elif gateway_type == GatewayType.WETH:
        return {
            "expectedL1Gateway": l2_network.token_bridge.l1_weth_gateway,
            "expectedL2Gateway": l2_network.token_bridge.l2_weth_gateway,
        }
    else:
        raise ArbSdkError(f"Unexpected gateway type: {gateway_type}")


async def deposit_token(
    deposit_amount,
    l1_token_address,
    erc20_bridger,
    l1_signer,
    l2_signer,
    expected_status,
    expected_gateway_type,
    retryable_overrides=None,
):
    _ = await erc20_bridger.approve_token(
        {
            "erc20L1Address": l1_token_address,
            "l1Signer": l1_signer,
        }
    )

    expected_l1_gateway_address = await erc20_bridger.get_l1_gateway_address(l1_token_address, l1_signer.provider)

    l1_token = erc20_bridger.get_l1_token_contract(l1_signer.provider, l1_token_address)

    allowance = l1_token.functions.allowance(l1_signer.account.address, expected_l1_gateway_address).call()

    assert allowance == Erc20Bridger.MAX_APPROVAL, "set token allowance failed"

    initial_bridge_token_balance = l1_token.functions.balanceOf(expected_l1_gateway_address).call()

    user_bal_before = l1_token.functions.balanceOf(l1_signer.account.address).call()

    deposit_rec = await erc20_bridger.deposit(
        {
            "l1Signer": l1_signer,
            "l2Provider": l2_signer.provider,
            "erc20L1Address": l1_token_address,
            "amount": deposit_amount,
            "retryableGasOverrides": retryable_overrides,
        }
    )

    final_bridge_token_balance = l1_token.functions.balanceOf(expected_l1_gateway_address).call()

    if expected_gateway_type == GatewayType.WETH:
        expected_balance = 0
    else:
        expected_balance = initial_bridge_token_balance + deposit_amount

    assert final_bridge_token_balance == expected_balance, "bridge balance not updated after L1 token deposit txn"

    user_bal_after = l1_token.functions.balanceOf(l1_signer.account.address).call()
    assert user_bal_after == user_bal_before - deposit_amount, "user bal after"

    wait_res = await deposit_rec.wait_for_l2(l2_signer)

    assert wait_res["status"] == expected_status, "Unexpected status"
    if retryable_overrides:
        return {"l1Token": l1_token, "waitRes": wait_res}

    gateways = get_gateways(expected_gateway_type, erc20_bridger.l2_network)
    l1_gateway = await erc20_bridger.get_l1_gateway_address(l1_token_address, l1_signer.provider)
    assert l1_gateway == gateways["expectedL1Gateway"], "incorrect l1 gateway address"

    l2_gateway = await erc20_bridger.get_l2_gateway_address(l1_token_address, l2_signer.provider)
    assert l2_gateway == gateways["expectedL2Gateway"], "incorrect l2 gateway address"

    l2_erc20_addr = await erc20_bridger.get_l2_erc20_address(l1_token_address, l1_signer.provider)

    l2_token = erc20_bridger.get_l2_token_contract(l2_signer.provider, l2_erc20_addr)

    l1_erc20_addr = await erc20_bridger.get_l1_erc20_address(l2_erc20_addr, l2_signer.provider)

    assert l1_erc20_addr == l1_token_address, "getERC20L1Address/getERC20L2Address failed with proper token address"

    test_wallet_l2_balance = l2_token.functions.balanceOf(l2_signer.account.address).call()

    assert test_wallet_l2_balance == deposit_amount, "l2 wallet not updated after deposit"

    return {"l1Token": l1_token, "waitRes": wait_res, "l2Token": l2_token}


def fund(signer, amount=None, funding_key=None):
    wallet = get_signer(signer.provider, funding_key)

    tx = {
        "from": wallet.address,
        "to": signer.account.address,
        "value": amount if amount else PRE_FUND_AMOUNT,
        "nonce": signer.provider.eth.get_transaction_count(wallet.address),
        "gasPrice": signer.provider.eth.gas_price,
        "chainId": signer.provider.eth.chain_id,
    }
    estimated_gas = signer.provider.eth.estimate_gas(tx)

    tx["gas"] = estimated_gas

    signed_tx = wallet.sign_transaction(tx)
    tx_hash = signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_receipt = signer.provider.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt


def fund_l1(l1_signer, amount=None):
    fund(l1_signer, amount, config["ETH_KEY"])


def fund_l2(l2_signer, amount=None):
    fund(l2_signer, amount, config["ARB_KEY"])


def wait(ms=0):
    time.sleep(ms / 1000)
