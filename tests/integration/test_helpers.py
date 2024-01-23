from web3 import Web3
from src.lib.data_entities.errors import ArbSdkError
from src.lib.asset_briger.erc20_bridger import Erc20Bridger
from src.lib.asset_briger.erc20_bridger import (
    MAX_APPROVAL,
    MIN_CUSTOM_DEPOSIT_GAS_LIMIT,
    MAX_UINT256,
)
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import CaseDict, deploy_abi_contract, load_contract
from src.scripts.test_setup import config, get_signer, test_setup
from src.lib.message.l2_to_l1_message import L2ToL1MessageStatus
from web3 import Account
import json

# Constants and utility functions
PRE_FUND_AMOUNT = Web3.to_wei(0.1, "ether")
arb_sys = "0x0000000000000000000000000000000000000064"


class GatewayType:
    STANDARD = 1
    CUSTOM = 2
    WETH = 3


async def mine_until_stop(miner, state):
    while state["mining"]:
        await miner.send_transaction({"to": miner.address, "value": 0})
        await wait(15000)


async def withdraw_token(params):
    withdrawal_params = await params["erc20_bridger"].get_withdrawal_request(
        {
            "amount": params["amount"],
            "erc20l1_address": params["l1_token"].address,
            "destination_address": await params["l2_signer"].get_address(),
            "from": await params["l2_signer"].get_address(),
        }
    )

    l1_gas_estimate = await withdrawal_params.estimate_l1_gas_limit(
        params["l1_signer"].provider
    )

    withdraw_res = await params["erc20_bridger"].withdraw(
        {
            "destination_address": await params["l2_signer"].get_address(),
            "amount": params["amount"],
            "erc20l1_address": params["l1_token"].address,
            "l2_signer": params["l2_signer"],
        }
    )

    withdraw_rec = await withdraw_res.wait()
    assert withdraw_rec["status"] == 1, "initiate token withdraw txn failed"

    message = (await withdraw_rec.get_l2_to_l1_messages(params["l1_signer"]))[0]
    assert message is not None, "withdraw message not found"

    message_status = await message.status(params["l2_signer"].provider)
    assert message_status == L2ToL1MessageStatus.UNCONFIRMED, "invalid withdraw status"

    l2_token_addr = await params["erc20_bridger"].get_l2_erc20_address(
        params["l1_token"].address, params["l1_signer"].provider
    )
    l2_token = params["erc20_bridger"].get_l2_token_contract(
        params["l2_signer"].provider, l2_token_addr
    )
    test_wallet_l2_balance = l2_token.functions.balanceOf(
        params["l2_signer"].account.address
    ).call()
    assert (
        test_wallet_l2_balance == params["start_balance"] - params["amount"]
    ), "token withdraw balance not deducted"

    wallet_address = await params["l1_signer"].get_address()
    gateway_address = await params["erc20_bridger"].get_l2_gateway_address(
        params["l1_token"].address, params["l2_signer"].provider
    )

    expected_l2_gateway = get_gateways(
        params["gateway_type"], params["erc20_bridger"].l2_network
    )["expected_l2_gateway"]
    assert gateway_address == expected_l2_gateway, "Gateway is not custom gateway"

    gateway_withdraw_events = await params["erc20_bridger"].get_l2_withdrawal_events(
        params["l2_signer"].provider,
        gateway_address,
        {"fromBlock": withdraw_rec["blockNumber"], "toBlock": "latest"},
        params["l1_token"].address,
        wallet_address,
    )
    assert len(gateway_withdraw_events) == 1, "token query failed"

    bal_before = (
        params["l1_token"]
        .functions.balanceOf(params["l1_signer"].account.address)
        .call()
    )

    # Mining simulation on L1 and L2
    # Replace this part with the actual logic for mining simulation or block advancement
    state = {"mining": True}
    # Simulate or wait for mining/block advancement here
    state["mining"] = False

    assert (
        await message.status(params["l2_signer"].provider)
        == L2ToL1MessageStatus.CONFIRMED
    ), "confirmed status"

    exec_tx = await message.execute(params["l2_signer"].provider)
    exec_rec = await exec_tx.wait()

    assert exec_rec["gasUsed"] <= l1_gas_estimate, "Gas used greater than estimate"
    assert (
        await message.status(params["l2_signer"].provider)
        == L2ToL1MessageStatus.EXECUTED
    ), "executed status"

    bal_after = (
        params["l1_token"]
        .functions.balanceOf(params["l1_signer"].account.address)
        .call()
    )
    assert bal_before + params["amount"] == bal_after, "Not withdrawn"


def get_gateways(gateway_type, l2_network):
    print("l2_network", l2_network)
    if gateway_type == GatewayType.CUSTOM:
        return {
            "expected_l1_gateway": l2_network.token_bridge.l1_custom_gateway,
            "expected_l2_gateway": l2_network.token_bridge.l2_custom_gateway,
        }
    elif gateway_type == GatewayType.STANDARD:
        return {
            "expected_l1_gateway": l2_network.token_bridge.l1_erc20_gateway,
            "expected_l2_gateway": l2_network.token_bridge.l2_erc20_gateway,
        }
    elif gateway_type == GatewayType.WETH:
        return {
            "expected_l1_gateway": l2_network.token_bridge.l1_weth_gateway,
            "expected_l2_gateway": l2_network.token_bridge.l2_weth_gateway,
        }
    else:
        raise ArbSdkError(f"Unexpected gateway type: {gateway_type}")


async def deposit_token(
    deposit_amount,
    l1_token_address,
    erc20_bridger,
    l1_signer: SignerOrProvider,
    l2_signer: SignerOrProvider,
    expected_status,
    expected_gateway_type,
    retryable_overrides=None,
):
    # Approve the ERC20 tokens for transfer by the bridge
    approval_tx = await erc20_bridger.approve_token(
        CaseDict(
            {
                "erc20_l1_address": l1_token_address,
                "l1Signer": l1_signer,
                "l1Provider": l1_signer.provider,
            }
        )
    )
    # await approval_tx.wait()
    print("approval_tx", approval_tx)

    # Get the address of the L1 gateway for the token
    expected_l1_gateway_address = await erc20_bridger.get_l1_gateway_address(
        l1_token_address, l1_signer.provider
    )

    # Retrieve the L1 token contract and check the allowance
    l1_token = erc20_bridger.get_l1_token_contract(l1_signer.provider, l1_token_address)

    allowance = l1_token.functions.allowance(
        l1_signer.account.address, expected_l1_gateway_address
    ).call()

    assert allowance == MAX_APPROVAL, "set token allowance failed"

    # Check the token balance in the bridge before the deposit
    initial_bridge_token_balance = l1_token.functions.balanceOf(
        expected_l1_gateway_address
    ).call()
    user_bal_before = l1_token.functions.balanceOf(l1_signer.account.address).call()

    # Make the deposit
    deposit_res = await erc20_bridger.deposit(
        CaseDict(
            {
                "l1_signer": l1_signer,
                "l2_provider": l2_signer.provider,
                "erc20_l1_address": l1_token_address,
                "amount": deposit_amount,
                "retryable_gas_overrides": retryable_overrides,
            }
        )
    )

    # Check the token balance in the bridge after the deposit
    final_bridge_token_balance = l1_token.functions.balanceOf(
        expected_l1_gateway_address
    ).call()
    assert (
        final_bridge_token_balance == initial_bridge_token_balance + deposit_amount
    ), "bridge balance not updated after L1 token deposit txn"

    # Check the user's balance after the deposit
    user_bal_after = l1_token.functions.balanceOf(l1_signer.account.address).call()
    assert user_bal_after == user_bal_before - deposit_amount, "user bal after"

    # Wait for the deposit to be recognized on L2
    wait_res = await deposit_res.wait_for_l2(l2_signer)
    print("wait_res", wait_res)
    assert wait_res["status"] == expected_status, "Unexpected status"
    if retryable_overrides:
        return wait_res
    # Verify the gateway addresses
    gateways = get_gateways(expected_gateway_type, erc20_bridger.l2_network)
    l1_gateway = await erc20_bridger.get_l1_gateway_address(
        l1_token_address, l1_signer.provider
    )
    assert l1_gateway == gateways["expected_l1_gateway"], "incorrect l1 gateway address"

    l2_gateway = await erc20_bridger.get_l2_gateway_address(
        l1_token_address, l2_signer.provider
    )
    assert l2_gateway == gateways["expected_l2_gateway"], "incorrect l2 gateway address"

    # Verify the token addresses and balances on L2
    l2_erc20_addr = await erc20_bridger.get_l2_erc20_address(
        l1_token_address, l1_signer.provider
    )
    l2_token = erc20_bridger.get_l2_token_contract(l2_signer.provider, l2_erc20_addr)
    l1_erc20_addr = await erc20_bridger.get_l1_erc20_address(
        l2_erc20_addr, l2_signer.provider
    )

    assert (
        l1_erc20_addr == l1_token_address
    ), "getERC20L1Address/getERC20L2Address failed with proper token address"

    test_wallet_l2_balance = l2_token.functions.balanceOf(
        l2_signer.account.address
    ).call()
    assert (
        test_wallet_l2_balance == deposit_amount
    ), "l2 wallet not updated after deposit"

    return {"l1_token": l1_token, "wait_res": wait_res, "l2_token": l2_token}


# def deposit_token(web3_instance, deposit_amount, l1_token_address, erc20_bridger, l1_signer_address, l2_signer_address, expected_status, expected_gateway_type):
#     # Create the ERC20 token contract instance
#     l1_token_contract = web3_instance.eth.contract(address=l1_token_address, abi=erc20_bridger.ERC20_ABI)

#     # Approve the ERC20 token for deposit
#     approve_tx = erc20_bridger.approve_token(web3_instance, l1_token_address, l1_signer_address, deposit_amount)
#     web3_instance.eth.wait_for_transaction_receipt(approve_tx)

#     # Fetch the expected L1 Gateway Address from the Erc20Bridger
#     expected_l1_gateway_address = erc20_bridger.get_l1_gateway_address(l1_token_address)

#     # Check the token allowance
#     allowance = l1_token_contract.functions.allowance(l1_signer_address, expected_l1_gateway_address).call()
#     assert allowance >= deposit_amount, "Token allowance is too low"

#     # Get the initial balance of the bridge contract
#     initial_bridge_token_balance = l1_token_contract.functions.balanceOf(expected_l1_gateway_address).call()

#     # Get the user's balance before the deposit
#     user_balance_before = l1_token_contract.functions.balanceOf(l1_signer_address).call()

#     # Perform the deposit
#     deposit_tx_receipt = erc20_bridger.deposit(web3_instance, l1_token_address, deposit_amount, l1_signer_address, l2_signer_address)

#     # Check the final balance of the bridge contract
#     final_bridge_token_balance = l1_token_contract.functions.balanceOf(expected_l1_gateway_address).call()
#     assert final_bridge_token_balance == initial_bridge_token_balance + deposit_amount, "Incorrect bridge balance after deposit"

#     # Check the user's balance after the deposit
#     user_balance_after = l1_token_contract.functions.balanceOf(l1_signer_address).call()
#     assert user_balance_after == user_balance_before - deposit_amount, "Incorrect user balance after deposit"

#     # Validate the deposit transaction
#     assert deposit_tx_receipt.status == expected_status, "Unexpected deposit transaction status"

#     # Additional checks and validations can be added here

#     return deposit_tx_receipt

# async def fund(signer, amount=None, funding_key=None):
#     # Assuming getSigner function exists to retrieve a wallet object
#     wallet = get_signer(signer.provider, funding_key)
#     await (await wallet.send_transaction({
#         'to': await signer.get_address(),
#         'value': amount or PRE_FUND_AMOUNT,
#     })).wait()


def fund(web3_instance, to_address, amount, funding_private_key=None):
    if funding_private_key is None:
        raise ValueError("Funding private key is required")

    # Create the account from the private key
    funding_account = Account.from_key(funding_private_key)

    # Fetch the current chain ID
    chain_id = web3_instance.eth.chain_id

    estimated_gas = web3_instance.eth.estimate_gas(
        {
            "from": funding_account.address,
            "to": to_address,
            "value": amount,
        }
    )

    # Build the transaction
    tx = {
        "nonce": web3_instance.eth.get_transaction_count(funding_account.address),
        "to": to_address,
        "value": amount,
        "gas": estimated_gas,  # Standard gas limit for Ether transfer
        "gasPrice": web3_instance.eth.gas_price,
        "chainId": chain_id,  # Include the chain ID
    }
    # Sign the transaction
    signed_tx = funding_account.sign_transaction(tx)

    # Send the transaction
    tx_hash = web3_instance.eth.send_raw_transaction(signed_tx.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = web3_instance.eth.wait_for_transaction_receipt(tx_hash)

    return tx_receipt


def fund_l1(l1_provider, l1_signer_address, amount=PRE_FUND_AMOUNT):
    fund(l1_provider, l1_signer_address, amount, config["ETH_KEY"])


def fund_l2(l2_provider, l2_signer, amount=PRE_FUND_AMOUNT):
    fund(l2_provider, l2_signer, amount, config["ARB_KEY"])


def wait(ms=0):
    import time

    time.sleep(ms / 1000)


def skip_if_mainnet(test_context):
    chain_id = None

    async def inner():
        nonlocal chain_id
        if chain_id is None:
            l1_network = await test_setup()
            chain_id = l1_network.chain_id
        if chain_id == 1:
            print("You're writing to the chain on mainnet lol stop")
            test_context.skip()

    return inner()


def mint_tokens(provider, contract_address, minter):
    contract = load_contract(
        provider=provider,
        contract_name="TestERC20",
        address=contract_address,
        is_classic=True,
    )

    # Fetch the current chain ID for EIP-155 replay protection
    chain_id = provider.eth.chain_id

    # Build the mint transaction
    mint_txn = contract.functions.mint().build_transaction(
        {
            "from": minter.address,
            "nonce": provider.eth.get_transaction_count(minter.address),
            # 'gas': gas_estimate, # Set appropriate gas limit
            "gasPrice": provider.eth.gas_price,
            "chainId": chain_id,  # Include the chain ID
        }
    )

    # Estimate gas for the mint transaction
    mint_txn["gas"] = provider.eth.estimate_gas(mint_txn)

    # Sign the transaction
    signed_txn = minter.sign_transaction(mint_txn)

    # Send the transaction
    tx_hash = provider.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = provider.eth.wait_for_transaction_receipt(tx_hash)
    return tx_receipt


def deploy_test_erc20(web3_instance, deployer):
    return deploy_abi_contract(web3_instance, deployer, "TestERC20", is_classic=True)
