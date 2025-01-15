"""
Utilities for handling and decoding transaction calldata in the Arbitrum SDK.

This module provides functions for extracting and decoding information from
transaction calldata, particularly for cross-chain token transfers between
L1 (Ethereum) and L2 (Arbitrum).
"""

from typing import Any, Optional, TypedDict

from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.utils.helper import create_contract_instance


class TxRequest(TypedDict):
    """Type definition for transaction request data."""

    data: str
    to: str
    value: int
    # Other transaction parameters can be added as needed


class ParentToChildTxReqAndSigner(TypedDict):
    """
    Type definition for a parent-to-child (L1 to L2) transaction request with signer.

    Attributes:
        txRequest: The transaction request parameters
        signer: The signer for the transaction (optional)
    """

    txRequest: TxRequest
    signer: Optional[Any]


def get_erc20_parent_address_from_parent_to_child_tx_request(
    tx_req: ParentToChildTxReqAndSigner,
) -> str:
    """
    Extract the ERC20 parent token address from a L1->L2 transaction request.

    This function decodes the transaction calldata to extract the token address
    from either 'outboundTransfer' or 'outboundTransferCustomRefund' function
    calls on the L1GatewayRouter contract.

    Args:
        tx_req (ParentToChildTxReqAndSigner): The transaction request containing the calldata.

    Returns:
        str: The ERC20 token address on L1 (parent chain)

    Raises:
        ArbSdkError: If the calldata doesn't match expected function signatures.
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
