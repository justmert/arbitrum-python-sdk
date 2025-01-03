from typing import List
from web3 import Web3
from web3.types import LogReceipt, LogCallable

from src.lib.utils.helper import CaseDict, load_abi


def parse_typed_log(
    provider: Web3,
    contract_name: str,
    log: dict,
    event_name: str,
    is_classic: bool = False
) -> CaseDict | None:
    """
    Parses a single log against a specific event name, returning the decoded args if it matches,
    or None if the topic does not match the event signature.

    :param provider: A Web3 provider instance.
    :param contract_name: The name of the contract. Must match a local ABI file.
    :param log: The log dictionary from a transaction receipt.
    :param event_name: The name of the event to decode (e.g. 'WithdrawalInitiated').
    :param is_classic: Whether to load the 'classic' or 'nitro' ABI (if relevant).
    :return: A CaseDict of decoded arguments if the log matches, else None.
    """
    # Load the contract ABI
    contract_abi, _ = load_abi(contract_name, is_classic=is_classic)
    contract = provider.eth.contract(abi=contract_abi)

    # Attempt to find the event in the ABI
    event_abi = next(
        (
            ev for ev in contract_abi
            if ev.get("type") == "event" and ev.get("name") == event_name
        ),
        None,
    )
    if not event_abi:
        # If the contract does not contain this event, return None
        return None

    # Construct the event signature via keccak
    event_signature = Web3.keccak(
        text=f"{event_name}({','.join([inp['type'] for inp in event_abi['inputs']])})"
    ).hex()

    # Compare the first topic of the log to the expected event signature
    if not log["topics"]:
        return None
    log_topic = Web3.to_hex(log["topics"][0])
    if log_topic.lower() != event_signature.lower():
        return None

    # If it matches, decode the log
    try:
        log_receipt = LogReceipt(log)
        # For dynamic event objects, we do contract.events.<EventName>:
        # but we can construct it with "contract.events[event_name]()"
        decoded_log = contract.events[event_name]().process_log(log_receipt)
        # Return arguments in a friendly CaseDict
        return CaseDict(decoded_log["args"])
    except Exception:
        # If decoding fails, we can either return None or raise the error
        return None


def parse_typed_logs(
    provider: Web3,
    contract_name: str,
    logs: List[dict],
    event_name: str,
    is_classic: bool = False
) -> List[CaseDict]:
    """
    Parses an array of logs, filtering out those whose topic does not match the
    provided event name topic, and decoding each matching log.

    :param provider: A Web3 provider instance.
    :param contract_name: The name of the contract, used to find its ABI.
    :param logs: A list of log dictionaries from a transaction receipt.
    :param event_name: The name of the event to decode (e.g. 'GatewaySet').
    :param is_classic: Whether to load the 'classic' or 'nitro' ABI.
    :return: A list of CaseDict objects containing the decoded arguments of matching logs.
    """
    results = []
    for log in logs:
        decoded = parse_typed_log(provider, contract_name, log, event_name, is_classic)
        if decoded is not None:
            results.append(decoded)
    return results
