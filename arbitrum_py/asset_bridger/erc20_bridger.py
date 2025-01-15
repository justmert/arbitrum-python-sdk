from collections import namedtuple
from typing import Any, Dict, List, Optional, TypeVar

from eth_abi import encode
from eth_typing import Address, HexStr
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import TxParams, Wei

from arbitrum_py.asset_bridger.asset_bridger import AssetBridger
from arbitrum_py.data_entities.constants import DISABLED_GATEWAY
from arbitrum_py.data_entities.errors import ArbSdkError, MissingProviderArbSdkError
from arbitrum_py.data_entities.networks import (
    ArbitrumNetwork,
    assert_arbitrum_network_has_token_bridge,
    get_arbitrum_network,
)
from arbitrum_py.data_entities.retryable_data import RetryableDataTools
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.data_entities.transaction_request import (
    ChildToParentTransactionRequest,
    ParentToChildTransactionRequest,
    is_child_to_parent_transaction_request,
    is_parent_to_child_transaction_request,
)
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from arbitrum_py.message.parent_to_child_message_gas_estimator import (
    GasOverrides,
    ParentToChildMessageGasEstimator,
)
from arbitrum_py.message.parent_transaction import ParentTransactionReceipt
from arbitrum_py.utils.calldata import (
    get_erc20_parent_address_from_parent_to_child_tx_request,
)
from arbitrum_py.utils.event_fetcher import EventFetcher
from arbitrum_py.utils.helper import (
    CaseDict,
    create_contract_instance,
    is_contract_deployed,
    load_contract,
)
from arbitrum_py.utils.lib import (
    get_native_token_decimals,
    is_arbitrum_chain,
    scale_from_18_decimals_to_native_token_decimals,
)

DepositParams = TypeVar("DepositParams")
WithdrawParams = TypeVar("WithdrawParams")


class Erc20Bridger(AssetBridger[DepositParams, WithdrawParams]):
    """Bridger for moving ERC20 tokens between parent and child chains.

    This class provides functionality for bridging ERC20 tokens between a parent chain
    (typically Ethereum mainnet) and a child chain (an Arbitrum chain). It handles
    token approvals, deposits, withdrawals, and gateway interactions.

    Attributes:
        MAX_APPROVAL (int): Maximum approval amount (2^256 - 1)
        MIN_CUSTOM_DEPOSIT_GAS_LIMIT (int): Minimum gas limit for custom token deposits
        child_network (ArbitrumNetwork): Network configuration for the child chain
        tokenBridge (TokenBridge): Token bridge configuration
    """

    MAX_APPROVAL: int = 2**256 - 1  # Equivalent of ethers MaxUint256
    MIN_CUSTOM_DEPOSIT_GAS_LIMIT: int = 275000

    def __init__(self, child_network: ArbitrumNetwork) -> None:
        """Initialize the ERC20 bridger.

        Args:
            child_network: ArbitrumNetwork instance containing chain configuration
                including chain IDs and token bridge details.

        Raises:
            ArbSdkError: If child_network lacks token bridge configuration
        """
        super().__init__(child_network)
        assert_arbitrum_network_has_token_bridge(child_network)
        self.child_network = child_network
        self.tokenBridge = child_network.tokenBridge

    @classmethod
    def from_provider(cls, child_provider: Web3) -> "Erc20Bridger":
        """Create an Erc20Bridger instance from a child chain provider.

        Args:
            child_provider: Web3 provider connected to the child chain

        Returns:
            Erc20Bridger: New bridger instance configured for the detected network

        Raises:
            ArbSdkError: If network detection fails or network is not supported
        """
        child_network = get_arbitrum_network(child_provider)
        return cls(child_network)

    def get_parent_gateway_address(self, erc20_parent_address: Address, parent_provider: Web3) -> Address:
        """Get the parent chain gateway address for a token.

        Args:
            erc20_parent_address: Address of the ERC20 token on parent chain
            parent_provider: Web3 provider for parent chain

        Returns:
            Address: Gateway contract address that handles this token

        Raises:
            ArbSdkError: If network validation fails or gateway lookup fails
        """
        self.check_parent_network(parent_provider)
        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.tokenBridge.parentGatewayRouter,
        )
        return parent_gateway_router.functions.getGateway(erc20_parent_address).call()

    def get_child_gateway_address(self, erc20_parent_address: Address, child_provider: Web3) -> Address:
        """Get the child chain gateway address for a token.

        Args:
            erc20_parent_address: Address of the ERC20 token on parent chain
            child_provider: Web3 provider for child chain

        Returns:
            Address: Gateway contract address that handles this token

        Raises:
            ArbSdkError: If network validation fails or gateway lookup fails
        """
        self.check_child_network(child_provider)
        child_gateway_router = load_contract(
            provider=child_provider,
            contract_name="L2GatewayRouter",
            address=self.tokenBridge.childGatewayRouter,
        )
        return child_gateway_router.functions.getGateway(erc20_parent_address).call()

    def get_approve_gas_token_request(self, params: Dict[str, Any]) -> TxParams:
        """Creates a transaction request for approving the custom gas token to be spent by the relevant gateway
        on the parent chain. If the chain uses ETH natively, this is unnecessary and will error.

        Args:
            params: A dict with 'erc20ParentAddress', 'parentProvider', 'amount' (optional), etc.

        Returns:
            dict representing a transaction request with 'to', 'data', and 'value'

        Raises:
            ValueError: If chain uses ETH as its native/gas token
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        tx_request = self.get_approve_token_request(params)
        # Overwrite the 'to' field to be the native token address
        return {**tx_request, "to": self.native_token}

    def approve_gas_token(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Approves the custom gas token to be spent by the relevant gateway on the parent chain.
        This only applies if the chain does NOT use ETH natively.

        Args:
            params: Dictionary that can either be:
                1) ApproveParams with 'erc20ParentAddress' and 'parentSigner'
                2) Or a transaction request dict with 'txRequest', 'parentSigner'

        Returns:
            Transaction receipt object from the parent chain

        Raises:
            ValueError: If chain uses ETH as its native/gas token
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        self.check_parent_network(params["parentSigner"])

        # Build or retrieve the transaction request
        if self.is_approve_params(params):
            # For the standard "approve gas token" flow
            approve_gas_token_request = self.get_approve_gas_token_request(
                {
                    **params,
                    "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
                }
            )
        else:
            # If user provided a custom transaction request
            approve_gas_token_request = params["txRequest"]

        transaction = {
            **approve_gas_token_request,
            **params.get("overrides", {}),
        }

        # If 'from' is missing, fill it in from the signer's address
        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        if "nonce" not in transaction:
            transaction["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in transaction:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(transaction)
            transaction["gas"] = gas_estimate

        if "gasPrice" not in transaction:
            if "maxPriorityFeePerGas" in transaction or "maxFeePerGas" in transaction:
                pass
            else:
                transaction["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in transaction:
            transaction["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(transaction)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def get_approve_token_request(self, params: Dict[str, Any]) -> TxParams:
        """Creates a transaction request to approve an ERC20 token for deposit.
        The tokens will be approved for whichever gateway the router returns.

        Args:
            params: A dict with 'erc20ParentAddress', 'parentProvider', optional 'amount', etc.

        Returns:
            A transaction request dict with 'to', 'data', 'value' = 0
        """
        gateway_address = self.get_parent_gateway_address(
            params["erc20ParentAddress"],
            SignerProviderUtils.get_provider_or_throw(params["parentProvider"]),
        )

        i_erc20_interface = create_contract_instance(
            contract_name="ERC20",
        )
        data = i_erc20_interface.encodeABI(
            fn_name="approve",
            args=[gateway_address, params.get("amount") or self.MAX_APPROVAL],
        )

        return {"to": params["erc20ParentAddress"], "data": data, "value": 0}

    def is_approve_params(self, params: Dict[str, Any]) -> bool:
        """Helper to check whether 'params' is a standard 'ApproveParams'
        (which includes 'erc20ParentAddress') vs. a custom txRequest.
        """
        return "erc20ParentAddress" in params

    def approve_token(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Approves the ERC20 token on the parent chain for bridging.

        Args:
            params: A dictionary that can either be standard 'ApproveParams'
                       or contain a pre-built 'txRequest'

        Returns:
            Transaction receipt from the parent chain
        """
        self.check_parent_network(params["parentSigner"])

        if self.is_approve_params(params):
            approve_request = self.get_approve_token_request(
                {
                    **params,
                    "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
                }
            )
        else:
            approve_request = params["txRequest"]

        transaction = {
            **approve_request,
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        if "nonce" not in transaction:
            transaction["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in transaction:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(transaction)
            transaction["gas"] = gas_estimate

        if "gasPrice" not in transaction:
            if "maxPriorityFeePerGas" in transaction or "maxFeePerGas" in transaction:
                pass
            else:
                transaction["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in transaction:
            transaction["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(transaction)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def get_withdrawal_events(
        self,
        child_provider: Web3,
        gateway_address: Address,
        filter_dict: Dict[str, Any],
        parent_token_address: Optional[Address] = None,
        from_address: Optional[Address] = None,
        to_address: Optional[Address] = None,
    ) -> List[Dict[str, Any]]:
        """Get the child network events (WithdrawalInitiated) created by a token withdrawal.

        Args:
            child_provider: Web3 provider for the child chain
            gateway_address: Address of the child gateway
            filter_dict: {'fromBlock': X, 'toBlock': Y}, specifying the block range
            parent_token_address: Optional filter for a specific parent token
            from_address: Optional filter for the "from" address
            to_address: Optional filter for the "to" address

        Returns:
            A list of event objects including 'txHash' for each withdrawal event
        """
        self.check_child_network(child_provider)
        event_fetcher = EventFetcher(child_provider)

        # We can extend argument_filters if needed
        argument_filters = {}
        # from_address, to_address, or parent_token_address can be further applied, but
        # for now we fetch all, then filter in Python for parent_token_address.

        events = event_fetcher.get_events(
            contract_factory="L2ArbitrumGateway",
            event_name="WithdrawalInitiated",
            argument_filters=argument_filters,
            filter={
                "address": gateway_address,
                **filter_dict,
            },
        )

        events = [{"txHash": a["transactionHash"], **a["event"]} for a in events]

        if parent_token_address:
            events = [ev for ev in events if ev["l1Token"].lower() == parent_token_address.lower()]
        # from_address / to_address filtering can be added as needed
        return events

    def looks_like_weth_gateway(self, potential_weth_gateway_address: Address, parent_provider: Web3) -> bool:
        """Ad-hoc check to see if the given address is a WETH gateway.
        We attempt to read the 'l1Weth()' method. If that fails with a call exception, it's not WETH.
        """
        try:
            potential_weth_gateway = load_contract(
                provider=parent_provider,
                contract_name="L1WethGateway",
                address=potential_weth_gateway_address,
            )
            potential_weth_gateway.functions.l1Weth().call()
            return True
        except ContractLogicError:
            return False
        except Exception as err:
            raise err

    def is_weth_gateway(self, gateway_address: Address, parent_provider: Web3) -> bool:
        """Check if a provided gateway address is the WETH gateway.

        Args:
            gateway_address: The suspected WETH gateway address
            parent_provider: Web3 provider for the parent chain

        Returns:
            bool
        """
        weth_address = self.child_network.tokenBridge.parentWethGateway
        if self.child_network.isCustom:
            # For custom networks, do a direct runtime check
            if self.looks_like_weth_gateway(gateway_address, parent_provider):
                return True
        else:
            # If it's not custom, compare directly to the known WETH gateway address
            if weth_address == gateway_address:
                return True
        return False

    def get_child_token_contract(self, child_provider: Web3, child_token_addr: Address) -> Contract:
        """Returns a contract object pointing to the child ERC20 token.
        Does not validate the contract code to confirm it's indeed an ERC20.
        """
        return load_contract(
            provider=child_provider,
            contract_name="L2GatewayToken",
            address=child_token_addr,
        )

    def get_parent_token_contract(self, parent_provider: Web3, parent_token_addr: Address) -> Contract:
        """Returns a contract object pointing to the parent ERC20 token."""
        return load_contract(
            provider=parent_provider,
            contract_name="ERC20",
            address=parent_token_addr,
        )

    def get_child_erc20_address(self, erc20_parent_address: Address, parent_provider: Web3) -> Address:
        """Given a parent chain token address, compute the corresponding child chain ERC20 token address.

        Args:
            erc20_parent_address: The parent chain token address
            parent_provider: A Web3 provider for the parent chain

        Returns:
            The corresponding child chain address
        """
        self.check_parent_network(parent_provider)

        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.tokenBridge.parentGatewayRouter,
        )
        return parent_gateway_router.functions.calculateL2TokenAddress(erc20_parent_address).call()

    def get_parent_erc20_address(self, erc20_child_chain_address: Address, child_provider: Web3) -> Address:
        """Given a child chain ERC20 token address, compute the corresponding parent chain token address.
        Also verify that the child chain router agrees on this mapping.

        Args:
            erc20_child_chain_address: The address of the token on the child chain
            child_provider: Web3 provider for the child chain

        Returns:
            The corresponding address on the parent chain

        Raises:
            ArbSdkError if the child token does not match the computed parent token
        """
        self.check_child_network(child_provider)

        # If this is the child WETH address, we can short-circuit
        if erc20_child_chain_address.lower() == self.child_network.tokenBridge.childWeth.lower():
            return self.child_network.tokenBridge.parentWeth

        arb_erc20 = load_contract(
            provider=child_provider,
            contract_name="L2GatewayToken",
            address=erc20_child_chain_address,
        )
        parent_address = arb_erc20.functions.l1Address().call()

        child_gateway_router = load_contract(
            provider=child_provider,
            contract_name="L2GatewayRouter",
            address=self.tokenBridge.childGatewayRouter,
        )
        child_address = child_gateway_router.functions.calculateL2TokenAddress(parent_address).call()

        if child_address.lower() != erc20_child_chain_address.lower():
            raise ArbSdkError(
                f"Unexpected parent address. Parent address from token is not registered to "
                f"the provided child address. {parent_address} {child_address} {erc20_child_chain_address}"
            )
        return parent_address

    def is_deposit_disabled(self, parent_token_address: Address, parent_provider: Web3) -> bool:
        """Whether the deposit for this token has been disabled on the parent router.

        Args:
            parent_token_address: The parent's ERC20 address
            parent_provider: Parent chain provider

        Returns:
            True if the token is disabled, False otherwise
        """
        self.check_parent_network(parent_provider)
        parent_gateway_router = load_contract(
            provider=parent_provider,
            contract_name="L1GatewayRouter",
            address=self.tokenBridge.parentGatewayRouter,
        )
        return parent_gateway_router.functions.l1TokenToGateway(parent_token_address).call() == DISABLED_GATEWAY

    def apply_defaults(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures default addresses for 'excessFeeRefundAddress', 'callValueRefundAddress',
        'destinationAddress' are set to 'from' if not otherwise specified.
        """
        return {
            **params,
            "excessFeeRefundAddress": (
                params["excessFeeRefundAddress"] if params.get("excessFeeRefundAddress") is not None else params["from"]
            ),
            "callValueRefundAddress": (
                params["callValueRefundAddress"] if params.get("callValueRefundAddress") is not None else params["from"]
            ),
            "destinationAddress": (
                params["destinationAddress"] if params.get("destinationAddress") is not None else params["from"]
            ),
        }

    def get_deposit_request_call_value(self, deposit_params: Dict[str, Any]) -> Wei:
        """Compute the ETH callValue needed for a deposit, if the chain uses ETH as its gas token.
        Otherwise, returns 0 because fees are handled differently.
        """
        if not self.native_token_is_eth:
            return 0
        return deposit_params["gasLimit"] * deposit_params["maxFeePerGas"] + deposit_params["maxSubmissionCost"]

    def get_deposit_request_outbound_transfer_inner_data(self, deposit_params: Dict[str, Any], decimals: int) -> HexStr:
        """Builds the 'innerData' argument for the gateway's outboundTransfer/outboundTransferCustomRefund calls.
        If the chain uses ETH natively, we pass [maxSubmissionCost, '0x'].
        Otherwise, also pack the fee inside.
        """

        if not self.native_token_is_eth:
            # For a chain that uses an ERC-20 gas token, we pass three fields:
            # [maxSubmissionCost, "0x", tokenTotalFee]
            fee_wei = deposit_params["gasLimit"] * deposit_params["maxFeePerGas"] + deposit_params["maxSubmissionCost"]
            encoded_values = self._solidity_encode(
                ["uint256", "bytes", "uint256"],
                [
                    int(deposit_params["maxSubmissionCost"]),
                    "0x",
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=fee_wei,
                        decimals=decimals,
                    ),
                ],
            )
            return encoded_values
        else:
            # For an ETH chain, only [maxSubmissionCost, "0x"] is needed
            encoded_values = self._solidity_encode(
                ["uint256", "bytes"],
                [
                    int(deposit_params["maxSubmissionCost"]),
                    "0x",
                ],
            )
            return encoded_values

    def get_deposit_request(self, params: Dict[str, Any]) -> ParentToChildTransactionRequest:
        """Constructs the deposit (parent->child) bridging transaction data.

        Args:
          params:
            {
            'from', 'parentProvider', 'childProvider',
            'erc20ParentAddress', 'amount', optional 'excessFeeRefundAddress',
            'callValueRefundAddress', 'destinationAddress', 'maxSubmissionCost',
            'retryableGasOverrides', ...
          }

        Returns:
            A ParentToChildTransactionRequest dict with 'txRequest', 'retryableData', 'isValid()'
        """
        self.check_parent_network(params["parentProvider"])
        self.check_child_network(params["childProvider"])

        defaulted_params = self.apply_defaults(params)

        amount = defaulted_params["amount"]
        destination_address = defaulted_params["destinationAddress"]
        erc20_parent_address = defaulted_params["erc20ParentAddress"]
        parent_provider = defaulted_params["parentProvider"]
        child_provider = defaulted_params["childProvider"]
        retryable_gas_overrides = defaulted_params.get("retryableGasOverrides", None)
        if retryable_gas_overrides is None:
            retryable_gas_overrides = {}

        # Possibly apply a custom min gas limit if this is the "custom" gateway
        parent_gateway_address = self.get_parent_gateway_address(erc20_parent_address, parent_provider)
        if parent_gateway_address == self.tokenBridge.parentCustomGateway:
            if "gasLimit" not in retryable_gas_overrides:
                retryable_gas_overrides["gasLimit"] = {}
            if "min" not in retryable_gas_overrides["gasLimit"]:
                retryable_gas_overrides["gasLimit"]["min"] = self.MIN_CUSTOM_DEPOSIT_GAS_LIMIT

        decimals = get_native_token_decimals(
            parent_provider=parent_provider,
            child_network=self.child_network,
        )

        def deposit_func(deposit_params: Dict[str, Any]) -> TxParams:
            """
            This local function returns the L1 transaction data for the deposit call on the L1GatewayRouter.
            """
            deposit_params["maxSubmissionCost"] = (
                params["maxSubmissionCost"]
                if params.get("maxSubmissionCost") is not None
                else deposit_params["maxSubmissionCost"]
            )
            inner_data = self.get_deposit_request_outbound_transfer_inner_data(deposit_params, decimals)

            # Load the L1GatewayRouter ABI interface
            i_gateway_router = create_contract_instance(
                # provider=parent_provider,
                contract_name="L1GatewayRouter",
            )
            # If user specified a non-default 'excessFeeRefundAddress'
            if defaulted_params["excessFeeRefundAddress"] != defaulted_params["from"]:

                # outboundTransferCustomRefund
                function_data = i_gateway_router.encodeABI(
                    fn_name="outboundTransferCustomRefund",
                    args=[
                        erc20_parent_address,
                        defaulted_params["excessFeeRefundAddress"],
                        destination_address,
                        amount,
                        deposit_params["gasLimit"],
                        deposit_params["maxFeePerGas"],
                        inner_data,
                    ],
                )
            else:
                # Standard outboundTransfer
                function_data = i_gateway_router.encodeABI(
                    fn_name="outboundTransfer",
                    args=[
                        erc20_parent_address,
                        destination_address,
                        amount,
                        deposit_params["gasLimit"],
                        deposit_params["maxFeePerGas"],
                        inner_data,
                    ],
                )

            return {
                "data": function_data,
                "to": self.tokenBridge.parentGatewayRouter,
                "from": defaulted_params["from"],
                "value": self.get_deposit_request_call_value(deposit_params),
            }

        # Use our ParentToChildMessageGasEstimator to figure out the final gas parameters
        gas_estimator = ParentToChildMessageGasEstimator(child_provider)

        estimates = gas_estimator.populate_function_params(
            deposit_func,
            parent_provider,
            retryable_gas_overrides,
        )

        def is_valid() -> bool:
            # Re-fetch estimates to see if they've changed
            re_estimates = gas_estimator.populate_function_params(
                deposit_func, parent_provider, retryable_gas_overrides
            )
            return ParentToChildMessageGasEstimator.is_valid(estimates["estimates"], re_estimates["estimates"])

        return CaseDict(
            {
                "txRequest": CaseDict(
                    {
                        "to": self.tokenBridge.parentGatewayRouter,
                        "data": estimates["data"],
                        "value": estimates["value"],
                        "from": params["from"],
                    }
                ),
                "retryableData": CaseDict({**estimates["retryable"], **estimates["estimates"]}),
                "isValid": is_valid,
            }
        )

    def deposit(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Execute a token deposit from the parent chain to the child chain.
        If the user has not provided a prebuilt transaction, we build it via get_deposit_request().

        Args:
            params: Erc20DepositParams (with 'parentSigner', 'childProvider', 'erc20ParentAddress', etc.)
                       OR a pre-built ParentToChildTxReqAndSignerProvider

        Returns:
            A ParentContractCallTransaction receipt-like object
        """

        self.check_parent_network(params["parentSigner"])

        # Safety check: the TS code disallows overriding 'value' in this call; do the same
        if "overrides" in params and params["overrides"] is not None and "value" in params["overrides"]:
            raise ArbSdkError("Parent call value should be set through l1CallValue param")

        parent_provider = SignerProviderUtils.get_provider_or_throw(params["parentSigner"])

        # If it's an actual "ParentToChildTransactionRequest", we can skip building the deposit.
        erc20_parent_address = (
            get_erc20_parent_address_from_parent_to_child_tx_request(params)
            if is_parent_to_child_transaction_request(params)
            else params["erc20ParentAddress"]
        )

        # Check if the token is fully registered
        is_registered = self.is_registered(
            {
                "erc20ParentAddress": erc20_parent_address,
                "parentProvider": parent_provider,
                "childProvider": params["childProvider"],
            }
        )
        if not is_registered:
            parent_chain_id = parent_provider.eth.chain_id
            raise ValueError(
                f"Token {erc20_parent_address} on chain {parent_chain_id} is not registered on the gateways"
            )

        # Build or retrieve the deposit transaction
        if is_parent_to_child_transaction_request(params):
            token_deposit = params
        else:
            token_deposit = self.get_deposit_request(
                {
                    **params,
                    "parentProvider": parent_provider,
                    "from": params["parentSigner"].account.address,
                }
            )

        transaction = {
            **token_deposit["txRequest"],
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        if "nonce" not in transaction:
            transaction["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in transaction:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(transaction)
            transaction["gas"] = gas_estimate

        if "gasPrice" not in transaction:
            if "maxPriorityFeePerGas" in transaction or "maxFeePerGas" in transaction:
                pass
            else:
                transaction["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in transaction:
            transaction["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(transaction)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_receipt = params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)

    def get_withdrawal_request(self, params: Dict[str, Any]) -> ChildToParentTransactionRequest:
        """Get the arguments for calling the token withdrawal function from the child chain.

        Args:
            params: Erc20WithdrawParams + 'from'

        Returns:
            ChildToParentTransactionRequest dict with 'txRequest' + optional 'estimateParentGasLimit'
        """
        to_address = params["destinationAddress"]

        # # We either have childProvider or childSigner
        # if "childProvider" in params:
        #     provider = params["childProvider"]
        # elif "childSigner" in params:
        #     provider = params["childSigner"].provider

        # Create function data for L2GatewayRouter.outboundTransfer
        router_interface = create_contract_instance(
            contract_name="L2GatewayRouter",
        )
        function_data = router_interface.encodeABI(
            fn_name="outboundTransfer",
            args=[
                params["erc20ParentAddress"],
                to_address,
                params["amount"],
                "0x",
            ],
        )

        def estimate_parent_gas_limit(parent_provider: Web3) -> int:
            """
            For display, we do a rough estimate of how many parent chain gas is needed
            once the L2->L1 message is executed.
            """
            if is_arbitrum_chain(parent_provider):
                # Hardcode for possible L3 scenario
                return 8_000_000

            parent_gateway_address = self.get_parent_gateway_address(
                params["erc20ParentAddress"],
                parent_provider,
            )
            is_weth = self.is_weth_gateway(parent_gateway_address, parent_provider)
            return 190000 if is_weth else 160000

        return {
            "txRequest": {
                "data": function_data,
                "to": self.tokenBridge.childGatewayRouter,
                "value": 0,
                "from": params["from"],
            },
            "estimateParentGasLimit": estimate_parent_gas_limit,
        }

    def withdraw(self, params: Dict[str, Any]) -> ChildTransactionReceipt:
        """Withdraw tokens from the child network back to the parent chain.

        Args:
          - Erc20WithdrawParams + childSigner
          - OR ChildToParentTxReqAndSigner

        Returns:
            A ChildContractTransaction receipt-like object
        """
        if not SignerProviderUtils.signer_has_provider(params["childSigner"]):
            raise MissingProviderArbSdkError("childSigner")

        self.check_child_network(params["childSigner"])

        # If user gave us a full "ChildToParentTransactionRequest", no need to build
        if is_child_to_parent_transaction_request(params):
            withdrawal_request = params
        else:
            withdrawal_request = self.get_withdrawal_request(
                {
                    **params,
                    "from": params["childSigner"].account.address,
                }
            )

        tx = {**withdrawal_request["txRequest"], **params.get("overrides", {})}
        if "from" not in tx:
            tx["from"] = params["childSigner"].account.address

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

        return ChildTransactionReceipt.monkey_patch_wait(tx_receipt)

    def is_registered(self, params: Dict[str, Any]) -> bool:
        """Checks if the token has been properly registered on both the parent and child gateways.
        Useful for tokens using a custom gateway.

        Args:
            params: {
              "erc20ParentAddress": str,
              "parentProvider": Web3,
              "childProvider": Web3
            }

        Returns:
            bool - True if the token is fully registered, False otherwise
        """
        parent_standard_gateway_address_from_chain_config = self.tokenBridge.parentErc20Gateway
        parent_gateway_address_from_parent_gateway_router = self.get_parent_gateway_address(
            params["erc20ParentAddress"], params["parentProvider"]
        )

        # If it's the standard gateway, we assume it's fine
        if (
            parent_standard_gateway_address_from_chain_config.lower()
            == parent_gateway_address_from_parent_gateway_router.lower()
        ):
            return True

        # Otherwise, we check the L2 token addresses from both parent and child router
        child_token_address_from_parent_gateway_router = self.get_child_erc20_address(
            params["erc20ParentAddress"],
            params["parentProvider"],
        )
        child_gateway_address_from_child_router = self.get_child_gateway_address(
            params["erc20ParentAddress"],
            params["childProvider"],
        )

        l2_erc20_gateway = load_contract(
            provider=params["childProvider"],
            contract_name="L2ERC20Gateway",
            address=child_gateway_address_from_child_router,
        )
        child_token_address_from_child_gateway = l2_erc20_gateway.functions.calculateL2TokenAddress(
            params["erc20ParentAddress"]
        ).call()

        return child_token_address_from_parent_gateway_router.lower() == child_token_address_from_child_gateway.lower()

    def _solidity_encode(self, types: List[str], values: List[Any]) -> HexStr:
        """
        Helper for ABI-encoding arbitrary fields for calls like outboundTransfer.
        Using eth_abi.encode(...) under the hood.
        """
        # Convert "0x" strings to empty bytes if needed
        processed_values = [val if val != "0x" else b"" for val in values]
        encoded_values = encode(types, processed_values)
        return encoded_values


class AdminErc20Bridger(Erc20Bridger):
    """
    Extended bridging class with admin functionality for registering custom tokens,
    setting gateways, etc.
    """

    def percent_increase(self, num: int, increase: int) -> int:
        return num + (num * increase) // 100

    def get_approve_gas_token_for_custom_token_registration_request(self, params: Dict[str, Any]) -> TxParams:
        """Similar to get_approve_gas_token_request, but used specifically for custom token registration.
        The difference is that we approve the parent token address itself to spend the gas token.
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        i_erc20_interface = create_contract_instance(
            contract_name="ERC20",
        )
        data = i_erc20_interface.encodeABI(
            fn_name="approve",
            args=[
                params["erc20ParentAddress"],
                params.get("amount") or self.MAX_APPROVAL,
            ],
        )

        return {
            "data": data,
            "value": 0,
            "to": self.native_token,
        }

    def approve_gas_token_for_custom_token_registration(self, params: Dict[str, Any]) -> ParentTransactionReceipt:
        """Approves the custom gas token for the given custom token's registration transaction.
        This is needed so we can pay fees using the custom gas token if the chain doesn't use ETH natively.
        """
        if self.native_token_is_eth:
            raise ValueError("Chain uses ETH as its native/gas token")

        self.check_parent_network(params["parentSigner"])

        if self.is_approve_params(params):
            approve_gas_token_request = self.get_approve_gas_token_for_custom_token_registration_request(
                {
                    **params,
                    "parentProvider": SignerProviderUtils.get_provider_or_throw(params["parentSigner"]),
                }
            )
        else:
            approve_gas_token_request = params["txRequest"]

        transaction = {
            **approve_gas_token_request,
            **params.get("overrides", {}),
        }

        if "from" not in transaction:
            transaction["from"] = params["parentSigner"].account.address

        if "nonce" not in transaction:
            transaction["nonce"] = params["parentSigner"].provider.eth.get_transaction_count(
                params["parentSigner"].account.address
            )

        if "gas" not in transaction:
            gas_estimate = params["parentSigner"].provider.eth.estimate_gas(transaction)
            transaction["gas"] = gas_estimate

        if "gasPrice" not in transaction:
            if "maxPriorityFeePerGas" in transaction or "maxFeePerGas" in transaction:
                pass
            else:
                transaction["gasPrice"] = params["parentSigner"].provider.eth.gas_price

        if "chainId" not in transaction:
            transaction["chainId"] = params["parentSigner"].provider.eth.chain_id

        signed_tx = params["parentSigner"].account.sign_transaction(transaction)
        tx_hash = params["parentSigner"].provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        return params["parentSigner"].provider.eth.wait_for_transaction_receipt(tx_hash)

    def register_custom_token(
        self,
        parent_token_address: Address,
        child_token_address: Address,
        parent_signer: Any,
        child_provider: Web3,
    ) -> ParentTransactionReceipt:
        """
        Register a custom (non-standard) token on Arbitrum. The token must already be deployed on both parent & child.
        The parent token must implement ICustomToken, and the child token must implement IArbToken.

        Args:
            parent_token_address: Address of the parent token contract on the parent chain
            child_token_address: Address of the child token contract on the child chain
            parent_signer: The signer object on the parent chain with permission to call registerTokenOnL2
            child_provider: A Web3 provider connected to the child chain

        Returns:
            A ParentTransactionReceipt object for the transaction
        """
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

        self.check_parent_network(parent_signer)
        self.check_child_network(child_provider)

        parent_provider = parent_signer.provider
        parent_sender_address = parent_signer.account.address

        # Load interfaces for the parent's ICustomToken & child's IArbToken
        parent_token = load_contract(
            provider=parent_provider,
            contract_name="ICustomToken",
            address=parent_token_address,
        )
        child_token = load_contract(
            provider=child_provider,
            contract_name="IArbToken",
            address=child_token_address,
        )

        # Ensure deployed
        if not is_contract_deployed(parent_provider, parent_token.address):
            raise ValueError("Parent token is not deployed.")
        if not is_contract_deployed(child_provider, child_token.address):
            raise ValueError("Child token is not deployed.")

        # Check allowance for paying fees (if chain uses custom token for gas)
        if not self.native_token_is_eth:
            native_token_contract = load_contract(
                provider=parent_provider,
                contract_name="ERC20",
                address=self.native_token,
            )
            allowance = native_token_contract.functions.allowance(
                parent_sender_address,
                parent_token.address,
            ).call()

            max_fee_per_gas_on_child = child_provider.eth.max_priority_fee
            max_fee_per_gas_on_child_with_buffer = self.percent_increase(max_fee_per_gas_on_child, 500)
            # Hardcode ~60k gas
            estimated_gas_fee = 60000 * max_fee_per_gas_on_child_with_buffer

            if allowance < estimated_gas_fee:
                raise ValueError(
                    f"Insufficient allowance. Please increase spending for: owner - {parent_sender_address}, "
                    f"spender - {parent_token.address}."
                )

        # Check the child's reported parent address
        parent_address_from_child = child_token.functions.l1Address().call()
        if parent_address_from_child != parent_token_address:
            raise ArbSdkError(
                f"Child token does not have parent address set. Found {parent_address_from_child}, "
                f"expected {parent_token_address}."
            )

        native_token_decimals = get_native_token_decimals(
            parent_provider=parent_provider, child_network=self.child_network
        )
        GasParams = namedtuple("GasParams", ["maxSubmissionCost", "gasLimit"])
        from_address = parent_signer.account.address

        def encode_func_data(set_token_gas: GasParams, set_gateway_gas: GasParams, max_fee_per_gas: int) -> TxParams:
            """
            Build the registerTokenOnL2(...) call for parentToken, including deposit amounts
            for each call (setToken call & setGateways call).
            """
            # If max_fee_per_gas is the error-triggering param, multiply by 2 to ensure it triggers for the second step
            if max_fee_per_gas == RetryableDataTools.ErrorTriggeringParams["maxFeePerGas"]:
                double_fee_per_gas = max_fee_per_gas * 2
            else:
                double_fee_per_gas = max_fee_per_gas

            set_token_deposit = set_token_gas.gasLimit * double_fee_per_gas + set_token_gas.maxSubmissionCost
            set_gateway_deposit = set_gateway_gas.gasLimit * double_fee_per_gas + set_gateway_gas.maxSubmissionCost

            encoded_data = parent_token.encodeABI(
                fn_name="registerTokenOnL2",
                args=[
                    child_token_address,
                    set_token_gas.maxSubmissionCost,
                    set_gateway_gas.maxSubmissionCost,
                    set_token_gas.gasLimit,
                    set_gateway_gas.gasLimit,
                    double_fee_per_gas,
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=set_token_deposit, decimals=native_token_decimals
                    ),
                    scale_from_18_decimals_to_native_token_decimals(
                        amount=set_gateway_deposit, decimals=native_token_decimals
                    ),
                    parent_sender_address,
                ],
            )

            return {
                "data": encoded_data,
                "to": parent_token.address,
                "value": (set_token_deposit + set_gateway_deposit if self.native_token_is_eth else 0),
                "from": from_address,
            }

        g_estimator = ParentToChildMessageGasEstimator(child_provider)

        # First call triggers the setToken logic
        set_token_estimates2 = g_estimator.populate_function_params(
            lambda p: encode_func_data(
                GasParams(p["maxSubmissionCost"], p["gasLimit"]),
                GasParams(
                    gasLimit=RetryableDataTools.ErrorTriggeringParams["gasLimit"],
                    maxSubmissionCost=1,
                ),
                p["maxFeePerGas"],
            ),
            parent_provider,
        )

        # Second call triggers the setGateways logic
        set_gateway_estimates2 = g_estimator.populate_function_params(
            lambda p: encode_func_data(
                GasParams(
                    set_token_estimates2["estimates"]["maxSubmissionCost"],
                    set_token_estimates2["estimates"]["gasLimit"],
                ),
                GasParams(p["maxSubmissionCost"], p["gasLimit"]),
                p["maxFeePerGas"],
            ),
            parent_provider,
        )

        register_tx = {
            "to": parent_token.address,
            "data": set_gateway_estimates2["data"],
            "value": set_gateway_estimates2["value"],
            "from": parent_signer.account.address,
        }

        if "nonce" not in register_tx:
            register_tx["nonce"] = parent_signer.provider.eth.get_transaction_count(parent_signer.account.address)

        if "gas" not in register_tx:
            gas_estimate = parent_signer.provider.eth.estimate_gas(register_tx)
            register_tx["gas"] = gas_estimate

        if "gasPrice" not in register_tx:
            if "maxPriorityFeePerGas" in register_tx or "maxFeePerGas" in register_tx:
                pass
            else:
                register_tx["gasPrice"] = parent_signer.provider.eth.gas_price

        if "chainId" not in register_tx:
            register_tx["chainId"] = parent_signer.provider.eth.chain_id

        signed_tx = parent_signer.account.sign_transaction(register_tx)
        tx_hash = parent_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        register_tx_receipt = parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_wait(register_tx_receipt)

    def get_parent_gateway_set_events(self, parent_provider: Web3, filter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get all the GatewaySet events on the parent chain's L1GatewayRouter within a given block range.

        Args:
            parent_provider: Web3 provider for parent chain
            filter_dict: {'fromBlock': X, 'toBlock': Y}

        Returns:
            List of the GatewaySet events
        """
        self.check_parent_network(parent_provider)

        parent_gateway_router_address = self.tokenBridge.parentGatewayRouter
        event_fetcher = EventFetcher(parent_provider)

        events = event_fetcher.get_events(
            contract_factory="L1GatewayRouter",
            event_name="GatewaySet",
            argument_filters={},
            filter={
                **filter_dict,
                "address": parent_gateway_router_address,
            },
        )

        return [a["event"] for a in events]

    def get_child_gateway_set_events(
        self,
        child_provider: Web3,
        filter_dict: Dict[str, Any],
        custom_network_child_gateway_router: Optional[Address] = None,
    ) -> List[Dict[str, Any]]:
        """Get all the GatewaySet events on the child chain's L2GatewayRouter within a given block range.

        Args:
            child_provider: Web3 provider for child chain
            filter_dict: {'fromBlock': X, 'toBlock': Y}
            custom_network_child_gateway_router: If the network is custom, we must pass the child router address

        Returns:
            List of the GatewaySet events

        Raises:
            ArbSdkError if the network is custom but the router address is not provided
        """
        if self.child_network.isCustom and not custom_network_child_gateway_router:
            raise ArbSdkError("Must supply customNetworkChildGatewayRouter for custom network ")

        self.check_child_network(child_provider)

        child_gateway_router_address = custom_network_child_gateway_router or self.tokenBridge.childGatewayRouter
        event_fetcher = EventFetcher(child_provider)

        events = event_fetcher.get_events(
            contract_factory="L2GatewayRouter",
            event_name="GatewaySet",
            argument_filters={},
            filter={
                **filter_dict,
                "address": child_gateway_router_address,
            },
        )
        return [a["event"] for a in events]

    def set_gateways(
        self,
        parent_signer: Any,
        child_provider: Web3,
        token_gateways: List[Dict[str, Address]],
        options: Optional[GasOverrides] = None,
    ) -> ParentTransactionReceipt:
        """Registers or updates multiple token->gateway mappings on the parent gateway router at once (admin call).

        Args:
            parent_signer: The signer on the parent chain
            child_provider: Web3 provider for the child chain
            token_gateways: A list of dicts with {"tokenAddr": X, "gatewayAddr": Y}
            options: Optional GasOverrides

        Returns:
            A ParentContractCallTransaction receipt
        """
        if not SignerProviderUtils.signer_has_provider(parent_signer):
            raise MissingProviderArbSdkError("parentSigner")

        self.check_parent_network(parent_signer)
        self.check_child_network(child_provider)

        from_address = parent_signer.account.address

        parent_gateway_router = load_contract(
            provider=parent_signer.provider,
            contract_name="L1GatewayRouter",
            address=self.tokenBridge.parentGatewayRouter,
        )

        def set_gateways_func(params: Dict[str, Any]) -> TxParams:
            return {
                "data": parent_gateway_router.encodeABI(
                    fn_name="setGateways",
                    args=[
                        [gw["tokenAddr"] for gw in token_gateways],
                        [gw["gatewayAddr"] for gw in token_gateways],
                        params["gasLimit"],
                        params["maxFeePerGas"],
                        params["maxSubmissionCost"],
                    ],
                ),
                "to": parent_gateway_router.address,
                "value": params["gasLimit"] * params["maxFeePerGas"] + params["maxSubmissionCost"],
                "from": from_address,
            }

        g_estimator = ParentToChildMessageGasEstimator(child_provider)
        estimates = g_estimator.populate_function_params(
            set_gateways_func,
            parent_signer.provider,
            options,
        )

        transaction = {
            "to": estimates["to"],
            "data": estimates["data"],
            "value": estimates["estimates"]["deposit"],
            "from": parent_signer.account.address,
        }

        if "nonce" not in transaction:
            transaction["nonce"] = parent_signer.provider.eth.get_transaction_count(parent_signer.account.address)

        if "gas" not in transaction:
            gas_estimate = parent_signer.provider.eth.estimate_gas(transaction)
            transaction["gas"] = gas_estimate

        if "gasPrice" not in transaction:
            if "maxPriorityFeePerGas" in transaction or "maxFeePerGas" in transaction:
                pass
            else:
                transaction["gasPrice"] = parent_signer.provider.eth.gas_price

        if "chainId" not in transaction:
            transaction["chainId"] = parent_signer.provider.eth.chain_id

        signed_tx = parent_signer.account.sign_transaction(transaction)
        tx_hash = parent_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_receipt = parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx_receipt)
