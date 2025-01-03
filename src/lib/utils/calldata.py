from typing import Any, Dict

from src.lib.utils.helper import load_contract
from src.lib.data_entities.errors import ArbSdkError


def get_erc20_parent_address_from_parent_to_child_tx_request(
    tx_req: Dict[str, Any],
) -> str:
    """
    Attempts to decode the transaction data from an L1->L2 deposit call 
    (i.e. 'outboundTransfer' or 'outboundTransferCustomRefund' function) to extract
    the ERC20 parent address (the '_token' argument).

    :param tx_req: A dictionary representing the transaction request object, 
                   typically the Python analog of ParentToChildTxReqAndSigner.
                   Must contain 'txRequest' -> 'data' as a hex string.
    :return: The `_token` address (string) if decoding succeeds.
    :raises ArbSdkError: If the txRequest.data cannot be decoded to the expected 
                         deposit function signatures.
    """
    # transaction data (hex string)
    data_hex = tx_req["txRequest"]["data"]

    # Load the L1GatewayRouter contract (assuming 'L1GatewayRouter' is the contract name 
    # and you have an ABI for it). Adjust if your naming scheme differs.
    l1_gateway_router = load_contract(
        provider=tx_req["parentSigner"].provider,  # or whichever provider you pass
        contract_name="L1GatewayRouter",
        is_classic=False,  # adjust as needed
    )

    # Try decoding the transaction data as 'outboundTransfer(...)'
    try:
        method_name, decoded_args = l1_gateway_router.decode_function_input(data_hex)
        # Check if the method_name is actually 'outboundTransfer'
        if method_name == "outboundTransfer":
            return decoded_args["_token"]
    except:
        pass

    # If the first attempt fails, try 'outboundTransferCustomRefund(...)'
    try:
        method_name, decoded_args = l1_gateway_router.decode_function_input(data_hex)
        # Check if the method_name is actually 'outboundTransferCustomRefund'
        if method_name == "outboundTransferCustomRefund":
            return decoded_args["_token"]
    except:
        pass

    # If neither decoding attempt succeeded, raise an error
    raise ArbSdkError("data signature not matching deposit methods")
