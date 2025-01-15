import threading
import time
from typing import Any, Dict, Optional
from eth_typing import Address
from web3 import Account, Web3
from web3.types import Wei

from scripts.setup_common import config, get_signer
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.message import ChildToParentMessageStatus
from arbitrum_py.data_entities.networks import (
    ArbitrumNetwork,
    assert_arbitrum_network_has_token_bridge,
)
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider
from arbitrum_py.utils.helper import load_contract
from arbitrum_py.utils.lib import scale_from_18_decimals_to_native_token_decimals
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import (
    is_arbitrum_network_with_custom_fee_token,
)

PRE_FUND_AMOUNT = Web3.to_wei(0.1, "ether")


def pretty_log(text: str) -> None:
    """Print formatted log message"""
    print(f"\n    *** {text}\n")


def warn(text: str) -> None:
    """Print warning message"""
    print(f"\nWARNING: {text}\n")


class GatewayType:
    STANDARD = 1
    CUSTOM = 2
    WETH = 3


def mine_until_stop(miner: SignerOrProvider, state: Dict[str, bool]) -> None:
    """Mine blocks until stopped"""
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


def withdraw_token(params: Dict[str, Any]) -> None:
    """
    Withdraw token from child to parent chain and validate the withdrawal

    Args:
        params: Dictionary containing:
            - amount: Amount to withdraw
            - erc20Bridger: ERC20 bridger instance
            - parentToken: Parent token contract
            - childSigner: Child chain signer
            - parentSigner: Parent chain signer
            - gatewayType: Expected gateway type
            - startBalance: Starting balance
    """
    withdrawal_params = params["erc20Bridger"].get_withdrawal_request(
        {
            "amount": params["amount"],
            "erc20ParentAddress": params["parentToken"].address,
            "destinationAddress": params["childSigner"].account.address,
            "from": params["childSigner"].account.address,
        }
    )

    parent_gas_estimate = withdrawal_params["estimateParentGasLimit"](params["parentSigner"].provider)

    withdraw_rec = params["erc20Bridger"].withdraw(
        {
            "destinationAddress": params["childSigner"].account.address,
            "amount": params["amount"],
            "erc20ParentAddress": params["parentToken"].address,
            "childSigner": params["childSigner"],
        }
    )

    assert withdraw_rec["status"] == 1, "initiate token withdraw txn failed"

    message = (withdraw_rec.get_child_to_parent_messages(params["parentSigner"]))[0]
    assert message is not None, "withdraw message not found"

    message_status = message.status(params["childSigner"].provider)
    assert message_status == ChildToParentMessageStatus.UNCONFIRMED, "invalid withdraw status"

    child_token_addr = params["erc20Bridger"].get_child_erc20_address(
        params["parentToken"].address, params["parentSigner"].provider
    )

    child_token = params["erc20Bridger"].get_child_token_contract(params["childSigner"].provider, child_token_addr)

    test_wallet_child_balance = child_token.functions.balanceOf(params["childSigner"].account.address).call()
    assert test_wallet_child_balance == params["startBalance"] - params["amount"], "token withdraw balance not deducted"

    gateway_address = params["erc20Bridger"].get_child_gateway_address(
        params["parentToken"].address, params["childSigner"].provider
    )

    expected_l2_gateway = get_gateways(params["gatewayType"], params["erc20Bridger"].child_network)["expectedL2Gateway"]
    assert gateway_address == expected_l2_gateway, "Gateway is not correct gateway"

    gateway_withdraw_events = params["erc20Bridger"].get_withdrawal_events(
        params["childSigner"].provider,
        gateway_address,
        {"fromBlock": withdraw_rec["blockNumber"], "toBlock": "latest"},
        params["parentToken"].address,
        params["parentSigner"].account.address,
    )
    assert len(gateway_withdraw_events) == 1, "token query failed"

    bal_before = params["parentToken"].functions.balanceOf(params["parentSigner"].account.address).call()

    # Set up mining threads
    miner1 = get_random_signer(params["parentSigner"].provider)
    miner2 = get_random_signer(params["childSigner"].provider)

    fund_parent_signer(miner1, Wei(Web3.to_wei(1, "ether")))
    fund_child_signer(miner2, Wei(Web3.to_wei(1, "ether")))

    state = {"mining": True}

    # Create mining threads
    miner1_thread = threading.Thread(target=mine_until_stop, args=(miner1, state))
    miner2_thread = threading.Thread(target=mine_until_stop, args=(miner2, state))
    message_thread = threading.Thread(
        target=lambda: message.wait_until_ready_to_execute(params["childSigner"].provider)
    )

    # Set threads as daemon to allow them to be terminated when main thread exits
    miner1_thread.daemon = True
    miner2_thread.daemon = True
    message_thread.daemon = True

    # Start all threads
    miner1_thread.start()
    miner2_thread.start()
    message_thread.start()

    # Wait for message to be ready
    message_thread.join()

    # Stop mining
    state["mining"] = False

    assert (message.status(params["childSigner"].provider)) == ChildToParentMessageStatus.CONFIRMED

    exec_rec = message.execute(params["childSigner"].provider)

    assert exec_rec["gasUsed"] <= parent_gas_estimate, "Gas used greater than estimate"

    assert (message.status(params["childSigner"].provider)) == ChildToParentMessageStatus.EXECUTED

    bal_after = params["parentToken"].functions.balanceOf(params["parentSigner"].account.address).call()
    assert bal_before + params["amount"] == bal_after, "Not withdrawn"


def get_gateways(gateway_type: int, child_network: ArbitrumNetwork) -> Dict[str, Address]:
    """Get gateway addresses based on gateway type"""
    assert_arbitrum_network_has_token_bridge(child_network)

    if gateway_type == GatewayType.CUSTOM:
        return {
            "expectedL1Gateway": child_network.token_bridge.parent_custom_gateway,
            "expectedL2Gateway": child_network.token_bridge.child_custom_gateway,
        }
    elif gateway_type == GatewayType.STANDARD:
        return {
            "expectedL1Gateway": child_network.token_bridge.parent_erc20_gateway,
            "expectedL2Gateway": child_network.token_bridge.child_erc20_gateway,
        }
    elif gateway_type == GatewayType.WETH:
        return {
            "expectedL1Gateway": child_network.token_bridge.parent_weth_gateway,
            "expectedL2Gateway": child_network.token_bridge.child_weth_gateway,
        }
    else:
        raise ArbSdkError(f"Unexpected gateway type: {gateway_type}")


def deposit_token(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deposit token from parent to child chain

    Args:
        params: Dictionary containing:
            - depositAmount: Amount to deposit
            - ethDepositAmount: Optional ETH amount to deposit
            - parentTokenAddress: Parent token address
            - erc20Bridger: ERC20 bridger instance
            - parentSigner: Parent chain signer
            - childSigner: Child chain signer
            - expectedStatus: Expected message status
            - expectedGatewayType: Expected gateway type
            - retryableOverrides: Optional gas overrides
            - destinationAddress: Optional destination address
    """
    fee_token_balance_before = None
    parent_signer = params["parentSigner"]
    child_signer = params["childSigner"]

    params["erc20Bridger"].approve_token(
        {"erc20ParentAddress": params["parentTokenAddress"], "parentSigner": parent_signer}
    )

    sender_address = parent_signer.account.address
    expected_parent_gateway_address = params["erc20Bridger"].get_parent_gateway_address(
        params["parentTokenAddress"], parent_signer.provider
    )
    parent_token = params["erc20Bridger"].get_parent_token_contract(
        parent_signer.provider, params["parentTokenAddress"]
    )

    allowance = parent_token.functions.allowance(sender_address, expected_parent_gateway_address).call()
    assert allowance == params["erc20Bridger"].MAX_APPROVAL, "set token allowance failed"

    if is_arbitrum_network_with_custom_fee_token():
        params["erc20Bridger"].approve_gas_token(
            {"parentSigner": parent_signer, "erc20ParentAddress": params["parentTokenAddress"]}
        )

        fee_token_contract = load_contract(
            provider=parent_signer.provider,
            contract_name="ERC20",
            address=params["erc20Bridger"].native_token,
        )

        fee_token_allowance = fee_token_contract.functions.allowance(
            sender_address, expected_parent_gateway_address
        ).call()

        assert fee_token_allowance == params["erc20Bridger"].MAX_APPROVAL, "set fee token allowance failed"

        fee_token_balance_before = fee_token_contract.functions.balanceOf(sender_address).call()

    initial_bridge_token_balance = parent_token.functions.balanceOf(expected_parent_gateway_address).call()

    parent_token_balance_before = parent_token.functions.balanceOf(sender_address).call()

    destination = params.get("destinationAddress", sender_address)
    child_eth_balance_before = child_signer.provider.eth.get_balance(destination)

    deposit_params = {
        "parentSigner": parent_signer,
        "childProvider": child_signer.provider,
        "erc20ParentAddress": params["parentTokenAddress"],
        "amount": params["depositAmount"],
        "retryableGasOverrides": params.get("retryableOverrides"),
        "maxSubmissionCost": params.get("ethDepositAmount"),
        "excessFeeRefundAddress": params.get("destinationAddress"),
        "destinationAddress": params.get("destinationAddress"),
    }

    deposit_rec = params["erc20Bridger"].deposit(deposit_params)

    final_bridge_token_balance = parent_token.functions.balanceOf(expected_parent_gateway_address).call()

    # WETH gateway withdraws ETH rather than transferring
    expected_balance = (
        0
        if params["expectedGatewayType"] == GatewayType.WETH
        else initial_bridge_token_balance + params["depositAmount"]
    )
    assert final_bridge_token_balance == expected_balance, "bridge balance not updated"

    parent_token_balance_after = parent_token.functions.balanceOf(sender_address).call()
    assert parent_token_balance_after == parent_token_balance_before - params["depositAmount"]

    if is_arbitrum_network_with_custom_fee_token():
        fee_token_balance_after = fee_token_contract.functions.balanceOf(sender_address).call()
        decimals = fee_token_contract.functions.decimals().call()

        MAX_BASE_ESTIMATED_GAS_FEE = Web3.to_wei(1, "gwei")
        max_scaled_estimated_gas_fee = scale_from_18_decimals_to_native_token_decimals(
            amount=MAX_BASE_ESTIMATED_GAS_FEE, decimals=decimals
        )

        gas_used = fee_token_balance_before - fee_token_balance_after
        assert gas_used <= max_scaled_estimated_gas_fee, "Too much custom fee token used as gas"

    wait_res = deposit_rec.wait_for_child_transaction_receipt(child_signer)

    child_eth_balance_after = child_signer.provider.eth.get_balance(destination)

    assert wait_res["status"] == params["expectedStatus"], "Unexpected status"

    if params.get("retryableOverrides"):
        return {"parentToken": parent_token, "waitRes": wait_res}

    # Gateway validation
    gateways = get_gateways(params["expectedGatewayType"], params["erc20Bridger"].child_network)

    parent_gateway = params["erc20Bridger"].get_parent_gateway_address(
        params["parentTokenAddress"], parent_signer.provider
    )
    assert parent_gateway == gateways["expectedL1Gateway"]

    child_gateway = params["erc20Bridger"].get_child_gateway_address(
        params["parentTokenAddress"], child_signer.provider
    )
    assert child_gateway == gateways["expectedL2Gateway"]

    # Token address checks
    child_token_addr = params["erc20Bridger"].get_child_erc20_address(
        params["parentTokenAddress"], parent_signer.provider
    )

    child_token = params["erc20Bridger"].get_child_token_contract(child_signer.provider, child_token_addr)

    parent_token_addr = params["erc20Bridger"].get_parent_erc20_address(child_token_addr, child_signer.provider)

    assert parent_token_addr == params["parentTokenAddress"]

    token_bal_on_child_after = child_token.functions.balanceOf(destination).call()

    # Only check for standard deposits
    if not params.get("destinationAddress") and not params.get("ethDepositAmount"):
        assert token_bal_on_child_after == params["depositAmount"]

    # Check ETH deposit if included
    if params.get("ethDepositAmount"):
        assert child_eth_balance_after >= child_eth_balance_before + params["ethDepositAmount"]

    return {"parentToken": parent_token, "waitRes": wait_res, "childToken": child_token}


def get_random_signer(provider):
    """Get a random signer connected to provider"""
    wallet = Account.create()
    return SignerOrProvider(wallet, provider)


def fund(signer: SignerOrProvider, amount: Optional[Wei] = None, funding_key: Optional[str] = None) -> None:
    """
    Fund an account

    Args:
        signer: Account to fund
        amount: Amount to fund (defaults to PRE_FUND_AMOUNT)
        funding_key: Private key of funding account
    """
    wallet = get_signer(signer.provider, funding_key)
    print(f"Funding {wallet.address} with {amount if amount else PRE_FUND_AMOUNT}")
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
    signer.provider.eth.wait_for_transaction_receipt(tx_hash)


def fund_parent_signer(parent_signer: SignerOrProvider, amount: Optional[Wei] = None) -> None:
    """Fund an account on parent chain"""
    fund(parent_signer, amount, config["ethKey"])


def fund_child_signer(child_signer: SignerOrProvider, amount: Optional[Wei] = None) -> None:
    """Fund an account on child chain"""
    fund(child_signer, amount, config["arbKey"])


def wait(ms: int = 0) -> None:
    """Wait for specified milliseconds"""
    time.sleep(ms / 1000)


def skip_if_mainnet() -> None:
    """Skip test if running on mainnet"""
    chain_id = None

    def _check(test_context):
        nonlocal chain_id
        if chain_id is None:
            test_setup = get_test_setup()
            chain_id = test_setup["childChain"].chain_id

        if chain_id in [42161, 42170]:  # Arbitrum One or Nova
            print("You're writing to the chain on mainnet lol stop")
            test_context.skip()

    return _check


def get_test_setup():
    """Get test setup for integration tests"""
    from scripts.test_setup import setup_testing_env

    return setup_testing_env()
