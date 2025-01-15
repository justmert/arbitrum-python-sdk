from typing import Any, Dict, Optional, TypeVar

from web3 import Web3
from web3.types import TxParams

from arbitrum_py.asset_bridger.asset_bridger import AssetBridger
from arbitrum_py.data_entities import constants
from arbitrum_py.data_entities.constants import ARB_SYS_ADDRESS
from arbitrum_py.data_entities.errors import MissingProviderArbSdkError
from arbitrum_py.data_entities.networks import ArbitrumNetwork, get_arbitrum_network
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.data_entities.transaction_request import (
    ChildToParentTransactionRequest,
    ParentToChildTransactionRequest,
    is_child_to_parent_transaction_request,
    is_parent_to_child_transaction_request,
)
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from arbitrum_py.message.parent_to_child_message_creator import (
    ParentToChildMessageCreator,
)
from arbitrum_py.message.parent_transaction import ParentTransactionReceipt
from arbitrum_py.utils.helper import create_contract_instance
from arbitrum_py.utils.lib import (
    get_native_token_decimals,
    is_arbitrum_chain,
    scale_from_native_token_decimals_to_18_decimals,
)

DepositParams = TypeVar("DepositParams")
WithdrawParams = TypeVar("WithdrawParams")


class EthBridger(AssetBridger[DepositParams, WithdrawParams]):
    """Bridger for moving ETH or custom gas tokens between parent and child networks.

    This class provides functionality for bridging ETH (or a custom gas token) between
    a parent chain (typically Ethereum mainnet) and a child chain (an Arbitrum chain).
    It handles token approvals, deposits, withdrawals, and inbox interactions.

    The bridger supports two main scenarios:
    1. Native ETH bridging when the chain uses ETH as its gas token
    2. Custom ERC20 token bridging when the chain uses a different token for gas

    Attributes:
        child_network (ArbitrumNetwork): Network configuration for the child chain
    """

    def __init__(self, child_network: ArbitrumNetwork) -> None:
        """Initialize the ETH bridger.

        Args:
            child_network: ArbitrumNetwork instance containing chain configuration
                including chain IDs and bridge details.
        """
        super().__init__(child_network)
        self.child_network = child_network

    @staticmethod
    def from_provider(child_provider: Web3) -> "EthBridger":
        """Create an EthBridger instance from a child chain provider.

        Args:
            child_provider: Web3 provider connected to the child chain

        Returns:
            EthBridger: New bridger instance configured for the detected network

        Raises:
            ArbSdkError: If network detection fails or network is not supported
        """
        network = get_arbitrum_network(child_provider)
        return EthBridger(network)

    def is_approve_gas_token_params(self, params: Dict[str, Any]) -> bool:
        """Check if params represent standard approve parameters vs custom transaction.

        Helper method to distinguish between an ApproveGasTokenParams dict and
        an ApproveGasTokenTxRequest dict.

        Args:
            params: Dictionary containing either standard approve parameters or
                a custom transaction request

        Returns:
            bool: True if params is ApproveGasTokenParams, False if ApproveGasTokenTxRequest
        """
        return "txRequest" not in params

    def get_approve_gas_token_request(self, params: Optional[Dict[str, Any]] = None) -> TxParams:
        """Create transaction request to approve custom gas token for bridging.

        Creates a transaction request object to approve a custom gas token (ERC20)
        for bridging on the parent chain. This is only needed when the chain uses
        an ERC20 token for gas instead of native ETH.

        Args:
            params: Optional dictionary containing:
                - amount: Amount to approve (defaults to MAX_UINT256)
                - parentProvider: Web3 provider for parent chain

        Returns:
            Transaction request object with 'to', 'data', and 'value' fields

        Raises:
            ValueError: If the chain uses ETH as its native gas token
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        erc20_interface = create_contract_instance(
            contract_name="ERC20",
        )
        amount = params.get("amount", constants.MAX_UINT256) if params else constants.MAX_UINT256

        data = erc20_interface.encodeABI(
            fn_name="approve",
            args=[
                self.child_network.ethBridge.inbox,
                amount,
            ],
        )

        return {
            "to": self.native_token,
            "data": data,
            "value": 0,
        }

    def approve_gas_token(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Approve custom gas token for spending by the Inbox contract.

        This method approves the custom gas token to be spent by the Inbox contract
        on the parent network. This is only necessary when the chain uses an ERC20
        token for gas instead of native ETH.

        Args:
            params: Dictionary containing either:
                1. Standard approve parameters:
                    - amount: (optional) Amount to approve
                    - parentSigner: Signer object for parent chain
                2. OR Custom transaction parameters:
                    - txRequest: Pre-built transaction request
                    - parentSigner: Signer object for parent chain
                    - overrides: (optional) Transaction overrides

        Returns:
            Transaction receipt from the approval transaction

        Raises:
            ValueError: If the chain uses ETH as its native gas token
            MissingProviderArbSdkError: If parentSigner lacks a provider
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        # Distinguish whether we have a custom transaction or standard params
        if self.is_approve_gas_token_params(params):
            approve_req = self.get_approve_gas_token_request(params)
        else:
            approve_req = params["txRequest"]

        # Merge any overrides and set the 'from' address
        tx = {
            **approve_req,
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        if "nonce" not in tx:
            tx["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in tx:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(tx)
            tx["gas"] = gas_estimate

        if "gasPrice" not in tx:
            if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
                pass
            else:
                tx["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in tx:
            tx["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(tx)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def get_deposit_request_data(self, params: Dict[str, Any]) -> bytes:
        """Create calldata for depositing ETH or custom gas token.

        Constructs the appropriate function call data for depositing either native ETH
        or a custom gas token, depending on the chain configuration.

        Args:
            params: Dictionary containing:
                - amount: Amount to deposit
                - parentProvider: (optional) Web3 provider for parent chain

        Returns:
            bytes: Encoded function call data for either depositEth() or depositERC20()
        """
        if not self.native_token_is_eth:
            erc20_inbox = create_contract_instance(
                contract_name="ERC20Inbox",
            )
            return erc20_inbox.encodeABI(
                fn_name="depositERC20",
                args=[params["amount"]],
            )

        inbox = create_contract_instance(
            contract_name="Inbox",
        )
        return inbox.encodeABI(fn_name="depositEth", args=[])

    def get_deposit_request(self, params: Dict[str, Any]) -> ParentToChildTransactionRequest:
        """Create transaction request for direct token deposit.

        Creates a transaction request for depositing ETH or a custom gas token directly
        into the child chain's inbox contract. This is used for the simple deposit
        scenario where tokens are minted to the same address on the child chain.

        Args:
            params: Dictionary containing:
                - amount: Amount to deposit
                - from: Address initiating the deposit
                - parentProvider: Web3 provider for parent chain

        Returns:
            Dictionary containing:
                - txRequest: Transaction parameters (to, value, data, from)
                - isValid: Function that returns True (simple deposit always valid)
        """
        return {
            "txRequest": {
                "to": self.child_network.ethBridge.inbox,
                "value": params["amount"] if self.native_token_is_eth else 0,
                "data": self.get_deposit_request_data(params),
                "from": params["from"],
            },
            "isValid": lambda: True,
        }

    def deposit(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Deposit ETH or custom gas token from parent to child chain.

        Executes a deposit transaction that moves ETH or custom gas token from the
        parent chain to the same address on the child chain. If a transaction request
        is not provided, one will be built using get_deposit_request().

        Args:
            params: Dictionary containing either:
                1. Standard deposit parameters:
                   - parentSigner: Signer object for parent chain
                   - amount: Amount to deposit
                   - overrides: (optional) Transaction overrides
                2. OR Custom transaction parameters:
                   - txRequest: Pre-built ParentToChildTransactionRequest
                   - parentSigner: Signer object for parent chain
                   - overrides: (optional) Transaction overrides

        Returns:
            Transaction receipt from the deposit transaction

        Raises:
            MissingProviderArbSdkError: If parentSigner lacks a provider
        """
        self.check_parent_network(params["parentSigner"])

        # If we have a ParentToChildTransactionRequest, skip building a deposit request
        if is_parent_to_child_transaction_request(params):
            eth_deposit = params
        else:
            eth_deposit = self.get_deposit_request({**params, "from": params["parentSigner"].account.address})

        tx = {
            **eth_deposit["txRequest"],
            **params.get("overrides", {}),
            "from": params["parentSigner"].account.address,
        }

        if "nonce" not in tx:
            tx["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in tx:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(tx)
            tx["gas"] = gas_estimate

        if "gasPrice" not in tx:
            if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
                pass
            else:
                tx["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in tx:
            tx["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(tx)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_receipt = params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        # monkeyPatchEthDepositWait => extended functionality for final wait or data decode
        return ParentTransactionReceipt.monkey_patch_eth_deposit_wait(tx_receipt)

    def get_deposit_to_request(self, params: Dict[str, Any]) -> ParentToChildTransactionRequest:
        """Create transaction request for depositing to a different address.

        Builds a transaction request for depositing ETH or a custom gas token from the
        parent chain to a different address on the child chain. This uses a retryable
        ticket flow under the hood.

        Args:
            params: Dictionary containing:
                - parentProvider: Web3 provider for parent chain
                - childProvider: Web3 provider for child chain
                - amount: Amount to deposit
                - destinationAddress: Address to receive the deposit on the child chain

        Returns:
            Dictionary containing:
                - txRequest: Transaction parameters (to, value, data, from)
                - retryableData: Retryable ticket data
        """
        decimals = get_native_token_decimals(parent_provider=params["parentProvider"], child_network=self.child_network)
        # Convert the deposit amount to 18 decimals for the child chain
        amount_to_be_minted_on_child_chain = scale_from_native_token_decimals_to_18_decimals(
            amount=params["amount"],
            decimals=decimals,
        )

        # The parentToChild retryable uses "l2CallValue" to define
        # how much ETH is minted or credited on L2
        request_params = {
            **params,
            "to": params["destinationAddress"],
            "l2CallValue": amount_to_be_minted_on_child_chain,
            "callValueRefundAddress": params["destinationAddress"],
            "data": "0x",
        }

        # Optional GasOverrides
        gas_overrides = params.get("retryableGasOverrides", {})

        return ParentToChildMessageCreator.get_ticket_creation_request(
            request_params,
            params["parentProvider"],
            params["childProvider"],
            gas_overrides,
        )

    def deposit_to(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Deposit ETH or custom gas token to a different address on the child chain.

        Executes a deposit transaction that moves ETH or custom gas token from the
        parent chain to a different address on the child chain. If a transaction request
        is not provided, one will be built using get_deposit_to_request().

        Args:
            params: Dictionary containing either:
                1. Standard deposit parameters:
                   - parentSigner: Signer object for parent chain
                   - childProvider: Web3 provider for child chain
                   - amount: Amount to deposit
                   - destinationAddress: Address to receive the deposit on the child chain
                   - overrides: (optional) Transaction overrides
                2. OR Custom transaction parameters:
                   - txRequest: Pre-built ParentToChildTransactionRequest
                   - parentSigner: Signer object for parent chain
                   - childProvider: Web3 provider for child chain
                   - overrides: (optional) Transaction overrides

        Returns:
            Transaction receipt from the deposit transaction

        Raises:
            MissingProviderArbSdkError: If parentSigner lacks a provider
        """
        self.check_parent_network(params["parentSigner"])
        self.check_child_network(params["childProvider"])

        # If it's already a ParentToChildTransactionRequest, skip
        if is_parent_to_child_transaction_request(params):
            retryable_ticket_request = params

        else:

            retryable_ticket_request = self.get_deposit_to_request(
                {
                    **params,
                    "from": params["parentSigner"].account.address,
                    "parentProvider": params["parentSigner"].provider,
                }
            )
        parent_to_child_msg_creator = ParentToChildMessageCreator(params["parentSigner"])

        tx = parent_to_child_msg_creator.create_retryable_ticket(
            retryable_ticket_request,
            params["childProvider"],
        )

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx)

    def get_withdrawal_request(self, params: Dict[str, Any]) -> ChildToParentTransactionRequest:
        """Create transaction request for withdrawing ETH from the child chain.

        Builds a transaction request for withdrawing ETH from the child chain back to
        the parent chain.

        Args:
            params: Dictionary containing:
                - childSigner or childProvider: Signer or provider for child chain
                - destinationAddress: Address to receive the withdrawal on the parent chain
                - amount: Amount to withdraw

        Returns:
            Dictionary containing:
                - txRequest: Transaction parameters (to, value, data, from)
                - estimateParentGasLimit: Function to estimate gas limit for parent chain
        """
        # The child side uses ArbSys.withdrawEth(...)
        arb_sys = create_contract_instance(
            contract_name="ArbSys",
            # address=ARB_SYS_ADDRESS,
        )

        function_data = arb_sys.encodeABI(
            fn_name="withdrawEth",
            args=[params["destinationAddress"]],
        )

        def estimate_parent_gas_limit(parent_provider) -> int:
            # For L3 scenario or if parent is actually an L2 chain
            if is_arbitrum_chain(parent_provider):
                return 4_000_000
            # Otherwise standard block on L1
            return 130000

        return {
            "txRequest": {
                "to": ARB_SYS_ADDRESS,
                "data": function_data,
                "value": params["amount"],
                "from": params["from"],
            },
            "estimateParentGasLimit": estimate_parent_gas_limit,
        }

    def withdraw(self, params: Dict[str, Any]) -> ChildTransactionReceipt:
        """Withdraw ETH from the child chain to the parent chain.

        Executes a withdrawal transaction that moves ETH from the child chain back to
        the parent chain. If a transaction request is not provided, one will be built
        using get_withdrawal_request().

        Args:
            params: Dictionary containing either:
                1. Standard withdrawal parameters:
                   - childSigner: Signer object for child chain
                   - destinationAddress: Address to receive the withdrawal on the parent chain
                   - amount: Amount to withdraw
                   - overrides: (optional) Transaction overrides
                2. OR Custom transaction parameters:
                   - txRequest: Pre-built ChildToParentTransactionRequest
                   - childSigner: Signer object for child chain
                   - overrides: (optional) Transaction overrides

        Returns:
            Transaction receipt from the withdrawal transaction

        Raises:
            MissingProviderArbSdkError: If childSigner lacks a provider
        """
        if not SignerProviderUtils.signer_has_provider(params["childSigner"]):
            raise MissingProviderArbSdkError("childSigner")

        self.check_child_network(params["childSigner"])

        if "from" not in params:
            params["from"] = params["childSigner"].account.address

        # If we already have a ChildToParentTransactionRequest, skip building it
        if is_child_to_parent_transaction_request(params):
            request = params
        else:
            request = self.get_withdrawal_request(params)

        tx = {
            **request["txRequest"],
            **params.get("overrides", {}),
        }
        if "nonce" not in tx:
            tx["nonce"] = params["childSigner"].provider.eth.get_transaction_count(
                params["childSigner"].account.address
            )

        if "gas" not in tx:
            gas_estimate = params["childSigner"].provider.eth.estimate_gas(tx)
            tx["gas"] = gas_estimate

        if "gasPrice" not in tx:
            if "maxPriorityFeePerGas" in tx or "maxFeePerGas" in tx:
                pass
            else:
                tx["gasPrice"] = params["childSigner"].provider.eth.gas_price

        if "chainId" not in tx:
            tx["chainId"] = params["childSigner"].provider.eth.chain_id

        signed_tx = params["childSigner"].account.sign_transaction(tx)
        tx_hash = params["childSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_receipt = params["childSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        # monkeyPatchWait => extended functionality for final wait or data decode
        return ChildTransactionReceipt.monkey_patch_wait(tx_receipt)
