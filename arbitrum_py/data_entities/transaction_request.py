from dataclasses import dataclass
from typing import Any, Callable, Dict, TypeVar, Union

from eth_typing import HexAddress, HexStr
from web3 import Web3
from web3.types import TxParams, Wei

from arbitrum_py.utils.lib import is_defined


@dataclass
class ParentToChildMessageParams:
    """Parameters for a message from parent chain to child chain.

    This class defines the parameters needed to describe a message call on the
    child chain (e.g., L2 in the case of Arbitrum).

    Attributes:
        to (HexAddress): The target address on the child chain
        callValue (Wei): The value in wei to be sent with the message
        callData (HexStr): The encoded function data to be executed
    """

    to: HexAddress
    callValue: Wei
    callData: HexStr


@dataclass
class ParentToChildMessageGasParams:
    """Gas parameters for parent to child chain message execution.

    This class defines the gas-related parameters needed for message execution
    on the child chain.

    Attributes:
        gasLimit (int): Maximum gas that can be used for execution
        maxFeePerGas (Wei): Maximum fee per gas unit willing to pay
        maxSubmissionCost (Wei): Maximum cost willing to pay for submission
    """

    gasLimit: int
    maxFeePerGas: Wei
    maxSubmissionCost: Wei


class ParentToChildTransactionRequest:
    """A transaction request that triggers execution on the child chain.

    This class represents transactions that initiate some execution on the child
    chain, such as L1->L2 message bridging operations in Arbitrum.

    The transaction consists of two main parts:
    1. The transaction request on the parent chain
    2. Parameters for the retryable ticket that will be created on the child chain

    Attributes:
        txRequest (TxParams): Core transaction fields for the parent chain
        retryableData (ParentToChildMessageParams & ParentToChildMessageGasParams):
            Parameters for the retryable ticket execution on the child chain

    Example:
        >>> txRequest = {
        ...     'to': '0x...',  # Bridge contract address
        ...     'data': '0x...',  # Encoded function data
        ...     'value': 1000000000000000000,  # 1 ETH
        ...     'from': '0x...'  # Sender address
        ... }
        >>> retryableData = {
        ...     'to': '0x...',  # L2 target
        ...     'callValue': 1000000000000000000,
        ...     'callData': '0x...',
        ...     'gasLimit': 100000,
        ...     'maxFeePerGas': 2000000000,
        ...     'maxSubmissionCost': 1000000000
        ... }
        >>> request = ParentToChildTransactionRequest(tx_request, retryable_data)
    """

    def __init__(self, tx_request: TxParams, retryable_data: Dict[str, Any]) -> None:
        """Initialize a new ParentToChildTransactionRequest.

        Args:
            txRequest: Transaction parameters for the parent chain
            retryableData: Parameters for the child chain execution

        Raises:
            ValueError: If required fields are missing from txRequest
        """
        required_fields = {"to", "data", "value", "from"}
        if not all(field in tx_request for field in required_fields):
            raise ValueError(f"txRequest missing required fields. Required: {required_fields}")

        self.tx_request = tx_request
        self.retryable_data = retryable_data

    def is_valid(self) -> bool:
        """Check if the transaction would have enough margin to succeed.

        This method verifies that the transaction parameters provide enough
        margin for reliable execution, checking aspects like:
        - Sufficient gas limits
        - Adequate maxSubmissionCost
        - Appropriate maxFeePerGas values

        Returns:
            bool: True if the transaction parameters provide enough margin
                for reliable execution, False otherwise
        """
        # TODO: Implement validation logic checking gas parameters
        return False


class ChildToParentTransactionRequest:
    """A transaction request that triggers a message from child to parent chain.

    This class represents transactions that initiate messages from the child
    chain to the parent chain, such as L2->L1 withdrawals in Arbitrum.

    Attributes:
        tx_request (TxParams): Core transaction fields for the child chain
        estimate_parent_gas_limit (Callable[[Web3], Wei]): Function to estimate
            the gas needed on the parent chain for message finalization

    Example:
        >>> def estimate_l1_gas(l1_provider: Web3) -> Wei:
        ...     # Estimate gas needed for L1 execution
        ...     return Wei(100000)
        ...
        >>> tx_request = {
        ...     'to': '0x...',  # L2 withdrawal contract
        ...     'data': '0x...',  # Encoded withdrawal data
        ...     'value': 1000000000000000000,  # 1 ETH
        ...     'from': '0x...'  # Sender address
        ... }
        >>> request = ChildToParentTransactionRequest(
        ...     tx_request,
        ...     estimate_l1_gas
        ... )
    """

    def __init__(self, tx_request: TxParams, estimate_parent_gas_limit: Callable[[Web3], Wei]) -> None:
        """Initialize a new ChildToParentTransactionRequest.

        Args:
            tx_request: Transaction parameters for the child chain
            estimate_parent_gas_limit: Function that estimates the gas needed
                for message finalization on the parent chain

        Raises:
            ValueError: If required fields are missing from tx_request
        """
        required_fields = {"to", "data", "value", "from"}
        if not all(field in tx_request for field in required_fields):
            raise ValueError(f"tx_request missing required fields. Required: {required_fields}")

        self.tx_request = tx_request
        self.estimate_parent_gas_limit = estimate_parent_gas_limit


T = TypeVar("T")


def is_parent_to_child_transaction_request(possible_request: Union[T, ParentToChildTransactionRequest]) -> bool:
    """Check if an object is a ParentToChildTransactionRequest.

    This function serves as both a runtime type check and a type guard
    in static type checking contexts.

    Args:
        possible_request: Object to check

    Returns:
        True if the object appears to be a ParentToChildTransactionRequest

    Example:
        >>> req = ParentToChildTransactionRequest(txRequest, retryable_data)
        >>> is_parent_to_child_transaction_request(req)  # True
        >>> is_parent_to_child_transaction_request({'other': 'data'})  # False
    """
    return is_defined(possible_request.get("txRequest", None))


def is_child_to_parent_transaction_request(possible_request: Union[T, ChildToParentTransactionRequest]) -> bool:
    """Check if an object is a ChildToParentTransactionRequest.

    This function serves as both a runtime type check and a type guard
    in static type checking contexts.

    Args:
        possible_request: Object to check

    Returns:
        True if the object appears to be a ChildToParentTransactionRequest

    Example:
        >>> req = ChildToParentTransactionRequest(txRequest, estimate_gas)
        >>> is_child_to_parent_transaction_request(req)  # True
        >>> is_child_to_parent_transaction_request({'other': 'data'})  # False
    """
    return is_defined(possible_request.get("txRequest", None))
