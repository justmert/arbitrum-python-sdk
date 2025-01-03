from eth_typing import HexAddress
from web3.types import Wei
from typing import Any, Dict, Callable, Awaitable, TypeVar, Union

from src.lib.utils.lib import is_defined


class ParentToChildMessageParams:
    pass


class ParentToChildMessageGasParams:
    pass


class ParentToChildTransactionRequest:
    """
    A transaction request for a transaction that will trigger some sort of
    execution on the child chain
    """
    def __init__(
        self, 
        tx_request: Dict[str, Any],
        retryable_data: Dict[str, Any]
    ):
        """
        Args:
            tx_request: Core fields needed to form the parent component of the transaction request
            retryable_data: Information about the retryable ticket and subsequent execution on child chain
        """
        self.tx_request = tx_request
        self.retryable_data = retryable_data

    async def is_valid(self) -> bool:
        """
        Check if this request has enough margin to reliably succeed if sent now
        
        Returns:
            bool: True if request would likely succeed, False otherwise
        """
        pass


class ChildToParentTransactionRequest:
    """
    A transaction request for a transaction that will trigger a child to parent message 
    """
    def __init__(
        self,
        tx_request: Dict[str, Any], 
        estimate_parent_gas_limit: Callable[[Any], Awaitable[Wei]]
    ):
        """
        Args:
            tx_request: Transaction request details
            estimate_parent_gas_limit: Function to estimate gas limit on parent chain
        """
        self.tx_request = tx_request
        self.estimate_parent_gas_limit = estimate_parent_gas_limit


T = TypeVar('T')

def is_parent_to_child_transaction_request(
    possible_request: Union[T, ParentToChildTransactionRequest]  
) -> bool:
    """
    Check if an object is of ParentToChildTransactionRequest type
    
    Args:
        possible_request: Object to check

    Returns:
        bool: True if object is ParentToChildTransactionRequest, False otherwise
    """
    return is_defined(getattr(possible_request, "txRequest", None))


def is_child_to_parent_transaction_request(
    possible_request: Union[T, ChildToParentTransactionRequest]
) -> bool:
    """
    Check if an object is of ChildToParentTransactionRequest type
    
    Args:
        possible_request: Object to check

    Returns:
        bool: True if object is ChildToParentTransactionRequest, False otherwise  
    """
    return is_defined(getattr(possible_request, "txRequest", None))