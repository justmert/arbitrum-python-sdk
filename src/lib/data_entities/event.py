from typing import Any, Dict, List

from web3 import Web3
from web3.exceptions import ABIFunctionNotFound, LogTopicError
from web3.types import LogReceipt

from src.lib.utils.helper import CaseDict, create_contract_instance, load_contract


def parse_typed_logs(
    contract_name: str,
    logs: List[Dict[str, Any]],
    event_name: str,
) -> List[Dict[str, Any]]:
    """
    Parse logs against a specific event name, returning decoded arguments.

    Args:
        contract_name: Name of the contract matching local ABI file
        logs: List of log dictionaries from transaction receipt
        event_name: Name of the event to decode (e.g. 'WithdrawalInitiated')

    Returns:
        List of decoded event arguments

    Raises:
        ValueError: If event not found in contract ABI
        ABIFunctionNotFound: If contract ABI is invalid
    """
    # Get contract ABI interface
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

    parsed_logs = []
    for log in logs:
        try:
            # Check if log matches event signature
            log_topic = Web3.to_hex(log["topics"][0])
            if log_topic and log_topic == event_signature:
                # Convert to LogReceipt format
                log_receipt = LogReceipt(log)

                # Process log
                try:
                    decoded_log = event().process_log(log_receipt)
                    parsed_logs.append(CaseDict(decoded_log["args"]))
                except (LogTopicError, ValueError) as e:
                    continue  # Skip logs that can't be decoded

        except (KeyError, IndexError):
            continue  # Skip malformed logs

    return parsed_logs


def get_event_signature(contract_name: str, event_name: str) -> str:
    """Helper to get event signature"""
    contract = load_contract(contract_name)
    event_abi = next((e for e in contract.abi if e.get("type") == "event" and e.get("name") == event_name), None)
    if not event_abi:
        raise ValueError(f"Event {event_name} not found")

    return Web3.keccak(text=f"{event_name}({','.join(inp['type'] for inp in event_abi['inputs'])})").hex()
