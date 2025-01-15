"""Event parsing utilities for Arbitrum SDK.

This module provides utilities for parsing and decoding Ethereum event logs,
with type-safe interfaces similar to TypeScript's TypedEvent system.
"""

from typing import Any, Dict, List, Optional, TypeVar, cast

from eth_typing import HexStr
from typing_extensions import Protocol, TypedDict
from web3 import Web3
from web3.exceptions import ABIFunctionNotFound, LogTopicError
from web3.types import EventData, LogReceipt

from arbitrum_py.utils.helper import CaseDict, create_contract_instance, load_contract


class EventArgs(TypedDict, total=False):
    """Base type for event arguments."""

    pass


T = TypeVar("T", bound=EventArgs)


class TypedEvent(Protocol[T]):
    """Protocol for typed events, similar to TypeScript's TypedEvent."""

    args: T


class ContractEventProcessor(Protocol):
    """Protocol for contract event processing interface."""

    def process_log(self, log: LogReceipt) -> EventData: ...
    def create_filter(self, *args: Any, **kwargs: Any) -> Any: ...


def parse_typed_log(
    contract_name: str,
    log: Dict[str, Any],
    event_name: str,
) -> Optional[Dict[str, Any]]:
    """Parse a single log entry against a specific event.

    This function attempts to decode a log entry using the specified event's ABI.
    If the log's topic matches the event signature, it returns the decoded arguments.

    Args:
        contract_name: Name of the contract containing the event definition
        log: Log dictionary from transaction receipt
        event_name: Name of the event to decode (e.g. 'WithdrawalInitiated')

    Returns:
        Decoded event arguments if log matches event signature, None otherwise

    Raises:
        ValueError: If event not found in contract ABI
        ABIFunctionNotFound: If contract ABI is invalid
    """
    contract = create_contract_instance(contract_name)

    try:
        event = getattr(contract.events, event_name)
    except ABIFunctionNotFound:
        raise ValueError(f"Event {event_name} not found in contract {contract_name}")

    # Get event signature
    event_abi = next((e for e in contract.abi if e.get("type") == "event" and e.get("name") == event_name), None)
    if not event_abi:
        raise ValueError(f"Event {event_name} not found in contract ABI")

    event_signature = Web3.keccak(text=f"{event_name}({','.join(inp['type'] for inp in event_abi['inputs'])})").hex()

    try:
        # Check if log matches event signature
        log_topic = Web3.to_hex(log["topics"][0])
        if log_topic and log_topic == event_signature:
            # Convert to LogReceipt format and process
            log_receipt = LogReceipt(log)
            try:
                decoded_log = event().process_log(log_receipt)
                return CaseDict(decoded_log["args"])
            except (LogTopicError, ValueError):
                return None
    except (KeyError, IndexError):
        return None

    return None


def parse_typed_logs(
    contract_name: str,
    logs: List[Dict[str, Any]],
    event_name: str,
) -> List[Dict[str, Any]]:
    """Parse multiple logs against a specific event.

    This function processes an array of logs, filtering out any that don't match
    the specified event's signature and decoding the matching ones.

    Args:
        contract_name: Name of the contract containing the event definition
        logs: List of log dictionaries from transaction receipt
        event_name: Name of the event to decode (e.g. 'WithdrawalInitiated')

    Returns:
        List of decoded event arguments from matching logs

    Raises:
        ValueError: If event not found in contract ABI
        ABIFunctionNotFound: If contract ABI is invalid
    """
    return [log_args for log in logs if (log_args := parse_typed_log(contract_name, log, event_name)) is not None]


def get_event_signature(contract_name: str, event_name: str) -> HexStr:
    """Get the keccak256 signature hash for an event.

    Computes the event signature by concatenating the event name with its
    parameter types and taking the keccak256 hash.

    Args:
        contract_name: Name of the contract containing the event
        event_name: Name of the event to get signature for

    Returns:
        Hex string of the event signature hash

    Raises:
        ValueError: If event not found in contract ABI
    """
    contract = load_contract(contract_name)
    event_abi = next((e for e in contract.abi if e.get("type") == "event" and e.get("name") == event_name), None)
    if not event_abi:
        raise ValueError(f"Event {event_name} not found in {contract_name}")

    signature = Web3.keccak(text=f"{event_name}({','.join(inp['type'] for inp in event_abi['inputs'])})").hex()
    return cast(HexStr, signature)
