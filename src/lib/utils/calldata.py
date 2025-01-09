from typing import Any, Dict

from src.lib.data_entities.errors import ArbSdkError
from src.lib.utils.helper import create_contract_instance


def get_erc20_parent_address_from_parent_to_child_tx_request(tx_req: Dict[str, Any]) -> str:
    """
    Extracts the ERC20 parent token address from a ParentToChildTxReqAndSigner transaction request.

    Args:
        tx_req (Dict[str, Any]): The transaction request containing the calldata.

    Returns:
        str: The ERC20 parent token address.

    Raises:
        ArbSdkError: If the calldata does not match expected function signatures.
    """
    data: str = tx_req["txRequest"]["data"]

    # Create the Contract instance without a provider
    l1_gateway_router = create_contract_instance("L1GatewayRouter")

    try:
        # Attempt to decode using 'outboundTransfer' function
        function, arguments = l1_gateway_router.decode_function_input(data)
        if function.fn_name == "outboundTransfer":
            return arguments["_token"]
        else:
            raise ArbSdkError("Decoded function name does not match 'outboundTransfer'")
    except Exception as e:
        # Log or handle the first decoding failure if necessary
        pass

    try:
        # Attempt to decode using 'outboundTransferCustomRefund' function
        function, arguments = l1_gateway_router.decode_function_input(data)
        if function.fn_name == "outboundTransferCustomRefund":
            return arguments["_token"]
        else:
            raise ArbSdkError("Decoded function name does not match 'outboundTransferCustomRefund'")
    except Exception as e:
        # Log or handle the second decoding failure if necessary
        pass

    # If neither decoding attempt was successful, raise an error
    raise ArbSdkError("data signature not matching deposits methods")
