from typing import Any, Dict, Callable, TypeVar, Union
from web3.types import Wei

from src.lib.utils.lib import is_defined


class ParentToChildMessageParams:
    """
    Placeholder for the parameters describing the message call on L2 
    (the 'to' address, callValue, etc).
    In the TS code, references a separate `ParentToChildMessageParams` interface.
    """
    pass


class ParentToChildMessageGasParams:
    """
    Placeholder for the gas parameters needed for L2 execution 
    (gasLimit, maxFeePerGas, etc).
    In the TS code, references `ParentToChildMessageGasParams` interface.
    """
    pass


class ParentToChildTransactionRequest:
    """
    A transaction request that triggers execution on the child chain 
    (for example, an L1->L2 bridging operation).
    It is the Python analog of the TS `ParentToChildTransactionRequest` interface.
    """

    def __init__(
        self,
        tx_request: Dict[str, Any],
        retryable_data: Dict[str, Any]
    ):
        """
        :param tx_request: 
            Core fields needed to form the parent component of the transaction 
            (like 'to', 'data', 'value', 'from').
        :param retryable_data: 
            A dict merging `ParentToChildMessageParams` & `ParentToChildMessageGasParams`.
        """
        self.tx_request = tx_request
        self.retryable_data = retryable_data

    def is_valid(self) -> bool:
        """
        If this request were sent now, would it have enough margin to reliably succeed?

        In TS, 'isValid()' returns `Promise<boolean>`.
        Here, we define it as returning bool.
        """
        # In actual usage, you'd implement checks on gas price, maxSubmissionCost, etc.
        return False


class ChildToParentTransactionRequest:
    """
    A transaction request that triggers a child->parent message 
    (for example, an L2->L1 withdrawal).
    Python analog of the TS `ChildToParentTransactionRequest`.
    """

    def __init__(
        self,
        tx_request: Dict[str, Any],
        estimate_parent_gas_limit: Callable[[Any], Wei]
    ):
        """
        :param tx_request: 
            A dict with minimal fields (like 'to', 'data', 'value', 'from') for the child chain transaction
        :param estimate_parent_gas_limit: 
            Function to estimate the gas limit required to finalize the message on the parent chain
        """
        self.tx_request = tx_request
        self.estimate_parent_gas_limit = estimate_parent_gas_limit


T = TypeVar('T')

def is_parent_to_child_transaction_request(
    possible_request: Union[T, ParentToChildTransactionRequest]
) -> bool:
    """
    Type guard / runtime check: is 'possible_request' a ParentToChildTransactionRequest?

    :param possible_request: The object to check.
    :return: True if it has a 'tx_request' attribute, else False.
    """
    return is_defined(getattr(possible_request, "tx_request", None))


def is_child_to_parent_transaction_request(
    possible_request: Union[T, ChildToParentTransactionRequest]
) -> bool:
    """
    Type guard / runtime check: is 'possible_request' a ChildToParentTransactionRequest?

    :param possible_request: The object to check.
    :return: True if it has a 'tx_request' attribute, else False.
    """
    return is_defined(getattr(possible_request, "tx_request", None))
