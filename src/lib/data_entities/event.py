from web3 import Web3
from web3.types import LogReceipt
from src.lib.utils.helper import load_abi

from test import CaseDict


def parse_typed_logs(provider, contract_name, logs, event_name, is_classic=False):
    contract_abi, _ = load_abi(contract_name, is_classic=is_classic)
    contract = provider.eth.contract(abi=contract_abi)

    event_abi = next(
        (event for event in contract_abi if event.get("name") == event_name and event.get("type") == "event"),
        None,
    )
    if not event_abi:
        print(f"Event {event_name} not found in ABI.")
        return []

    event_signature = Web3.keccak(
        text=f"{event_name}({','.join([input['type'] for input in event_abi['inputs']])})"
    ).hex()

    parsed_logs = []
    for log in logs:
        log_topic = Web3.to_hex(log["topics"][0])
        if log_topic and log_topic == event_signature:
            try:
                print(f"Matched! Log's Topic: 0x{log_topic} == Computed Signature: 0x{event_signature}")
                log_receipt = LogReceipt(log)
                decoded_log = contract.events[event_name]().process_log(log_receipt)
                parsed_logs.append(CaseDict(decoded_log["args"]))
            except Exception as e:
                print(f"Failed to decode log: {e}")
                raise e
            else:
                print(f"Decoded log: {parsed_logs[-1]}")
    return parsed_logs
