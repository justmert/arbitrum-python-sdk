"""
Utility functions for the Arbitrum SDK.

This module provides common utility functions for:
- Chain interaction (getting base fees, transaction receipts)
- Block management (finding L1/L2 block correspondences)
- Token decimals handling
- General utilities (waiting, type checking)
"""

import time
from typing import Optional, Tuple, TypeVar, Union, cast

from eth_typing import BlockNumber, HexStr
from web3 import Web3
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt, Wei

from arbitrum_py.data_entities.constants import ADDRESS_ZERO, ARB_SYS_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.networks import ArbitrumNetwork, get_nitro_genesis_block
from arbitrum_py.utils.helper import load_contract

T = TypeVar("T")  # For generic type hints


def wait(ms: int) -> None:
    """
    Wait for the specified number of milliseconds.

    Args:
        ms: Time in milliseconds to sleep

    Example:
        >>> wait(1000)  # Wait for 1 second
    """
    time.sleep(ms / 1000)


def get_base_fee(provider: Web3) -> Wei:
    """
    Retrieve the base fee per gas from the latest block.

    Args:
        provider: A Web3 provider connected to an EIP-1559 chain

    Returns:
        The base fee in Wei

    Raises:
        ArbSdkError: If baseFeePerGas is not found (e.g., non-EIP1559 chain)

    Example:
        >>> base_fee = get_base_fee(web3)
        >>> print(f"Current base fee: {Web3.from_wei(base_fee, 'gwei')} gwei")
    """
    try:
        latest_block = provider.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is None:
            raise ArbSdkError(
                "Latest block did not contain base fee. "
                "Ensure provider is connected to an EIP-1559-compatible chain."
            )
        return Wei(base_fee)
    except Exception as e:
        raise ArbSdkError(f"Failed to get base fee: {str(e)}") from e


def get_transaction_receipt(
    provider: Web3,
    tx_hash: HexStr,
    confirmations: Optional[int] = None,
    timeout: Optional[int] = None,
) -> Optional[TxReceipt]:
    """
    Retrieve a transaction receipt with optional confirmation count or timeout.

    This function can operate in two modes:
    1. Immediate retrieval (no confirmations/timeout)
    2. Wait for confirmations or timeout

    Args:
        provider: Web3 provider instance
        tx_hash: Transaction hash to fetch
        confirmations: Number of block confirmations to wait for
        timeout: Maximum time to wait in milliseconds

    Returns:
        The transaction receipt if found and confirmed, None otherwise

    Raises:
        Exception: Any unexpected errors during receipt retrieval

    Example:
        >>> # Wait for 2 confirmations with 30 second timeout
        >>> receipt = get_transaction_receipt(
        ...     web3,
        ...     "0x...",
        ...     confirmations=2,
        ...     timeout=30000
        ... )
    """

    if confirmations or timeout:
        try:
            # Convert timeout from ms to seconds if provided
            timeout_seconds = (timeout / 1000) if timeout else None

            receipt = provider.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout_seconds)

            if confirmations:
                latest_block_num = provider.eth.block_number
                if latest_block_num - receipt.blockNumber < confirmations:
                    return None
            return receipt
        except TimeExhausted:
            return None
        except Exception as e:
            raise ArbSdkError(f"Error waiting for transaction receipt: {str(e)}") from e
    else:
        try:
            return provider.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None
        except Exception as e:
            raise ArbSdkError(f"Error getting transaction receipt: {str(e)}") from e


def is_defined(value: Optional[T]) -> bool:
    """
    Check if a value is defined (not None).

    This is the Python equivalent of TypeScript's isDefined type guard.

    Args:
        value: Any value to check

    Returns:
        True if the value is not None, False otherwise

    Example:
        >>> assert is_defined(0) is True
        >>> assert is_defined(None) is False
    """
    return value is not None


def is_arbitrum_chain(provider: Web3) -> bool:
    """
    Check if a provider is connected to an Arbitrum chain.

    This function attempts to call arbOSVersion on the ArbSys precompile,
    which only exists on Arbitrum chains.

    Args:
        provider: Web3 provider to check

    Returns:
        True if connected to an Arbitrum chain, False otherwise

    Example:
        >>> # Check if connected to Arbitrum
        >>> if is_arbitrum_chain(web3):
        ...     print("Connected to Arbitrum!")
    """
    try:
        arb_sys = load_contract(
            provider=provider,
            contract_name="ArbSys",
            address=ARB_SYS_ADDRESS,
        )
        arb_sys.functions.arbOSVersion().call()
        return True
    except Exception:
        return False


def get_first_block_for_l1_block(
    arbitrum_provider: Web3,
    for_l1_block: BlockNumber,
    allow_greater: bool = False,
    min_arbitrum_block: Optional[BlockNumber] = None,
    max_arbitrum_block: Union[BlockNumber, str] = "latest",
) -> Optional[BlockNumber]:
    """
    Find the first Arbitrum (L2) block that corresponds to a given L1 block.

    This function performs a binary search over the L2 chain to find the first block
    that references the given L1 block number. If allow_greater is True, it will
    return the first L2 block with an L1 block number >= the target.

    Args:
        arbitrum_provider: Web3 provider connected to Arbitrum
        for_l1_block: Target L1 block number to find correspondence for
        allow_greater: If True, allow returning a block with higher L1 number
        min_arbitrum_block: Minimum L2 block to consider (defaults to Nitro genesis)
        max_arbitrum_block: Maximum L2 block or 'latest'

    Returns:
        The L2 block number if found, None otherwise

    Raises:
        ArbSdkError: If invalid block range or provider configuration

    Example:
        >>> l2_block = get_first_block_for_l1_block(
        ...     web3,
        ...     for_l1_block=15000000,
        ...     allow_greater=True
        ... )
    """
    if not is_arbitrum_chain(arbitrum_provider):
        # If on L1, just return the same block number
        return cast(BlockNumber, for_l1_block)

    arb_provider = arbitrum_provider
    current_arb_block = arb_provider
    chain_id = arb_provider.eth.chain_id
    nitro_genesis = get_nitro_genesis_block(chain_id)

    def get_l1_block(l2_block: int) -> Optional[int]:
        block = arb_provider.eth.get_block(l2_block)
        return int(block.get("l1BlockNumber"), 16)

    # Set default min block to Nitro genesis if not specified
    if min_arbitrum_block is None:
        min_arbitrum_block = BlockNumber(nitro_genesis)

    # Convert 'latest' to current block number
    if max_arbitrum_block == "latest":
        max_arbitrum_block = BlockNumber(current_arb_block)

    # Validate block range
    if min_arbitrum_block >= max_arbitrum_block:
        raise ArbSdkError(f"Invalid block range: min ({min_arbitrum_block}) >= " f"max ({max_arbitrum_block})")

    if min_arbitrum_block < nitro_genesis:
        raise ArbSdkError(
            f"min_arbitrum_block ({min_arbitrum_block}) cannot be below " f"Nitro genesis block ({nitro_genesis})"
        )

    start = min_arbitrum_block
    end = max_arbitrum_block
    result_for_target = None
    result_for_greater = None

    while start <= end:
        mid = start + (end - start) // 2
        l1_block_of_mid = get_l1_block(mid)
        if l1_block_of_mid == for_l1_block:
            result_for_target = mid
            end = mid - 1
        elif l1_block_of_mid < for_l1_block:
            start = mid + 1
        else:
            # l1_block_of_mid > for_l1_block
            end = mid - 1
            if allow_greater:
                result_for_greater = mid

    return result_for_target or result_for_greater


def get_block_ranges_for_l1_block(
    arbitrum_provider: Web3,
    for_l1_block: BlockNumber,
    allow_greater: bool = False,
    min_arbitrum_block: Optional[BlockNumber] = None,
    max_arbitrum_block: Union[BlockNumber, str] = "latest",
) -> Tuple[Optional[BlockNumber], Optional[BlockNumber]]:
    """
    Find the range of Arbitrum blocks corresponding to an L1 block.

    This function finds both the first and last L2 blocks that correspond
    to a given L1 block number.

    Args:
        arbitrum_provider: Web3 provider connected to Arbitrum
        for_l1_block: Target L1 block to find range for
        allow_greater: If True, allow blocks with higher L1 numbers
        min_arbitrum_block: Minimum L2 block to consider
        max_arbitrum_block: Maximum L2 block or 'latest'

    Returns:
        Tuple of (start_block, end_block), both None if not found

    Example:
        >>> start, end = get_block_ranges_for_l1_block(
        ...     web3,
        ...     for_l1_block=15000000
        ... )
        >>> if start and end:
        ...     print(f"L2 blocks {start} to {end} correspond to L1 block 15000000")
    """

    current_l2_block = arbitrum_provider.eth.block_number

    if not max_arbitrum_block or max_arbitrum_block == "latest":
        max_arbitrum_block = BlockNumber(current_l2_block)

    # Get start and end of range
    results = [
        get_first_block_for_l1_block(
            arbitrum_provider,
            for_l1_block,
            allow_greater=False,
            min_arbitrum_block=min_arbitrum_block,
            max_arbitrum_block=max_arbitrum_block,
        ),
        get_first_block_for_l1_block(
            arbitrum_provider,
            BlockNumber(for_l1_block + 1),
            allow_greater=True,
            min_arbitrum_block=min_arbitrum_block,
            max_arbitrum_block=max_arbitrum_block,
        ),
    ]

    if not results[0]:
        return None, None

    if results[0] and results[1]:
        return results[0], BlockNumber(results[1] - 1)

    return results[0], cast(BlockNumber, max_arbitrum_block)


def get_native_token_decimals(parent_provider: Web3, child_network: ArbitrumNetwork) -> int:
    """
    Get the number of decimals for the chain's native token.

    For ETH or zero address, returns 18. Otherwise queries the token contract.

    Args:
        parent_provider: Web3 provider for parent chain
        child_network: ArbitrumNetwork configuration

    Returns:
        Number of decimals for the native token

    Raises:
        ArbSdkError: If unable to determine token decimals

    Example:
        >>> decimals = get_native_token_decimals(web3, network)
        >>> print(f"Native token has {decimals} decimals")
    """
    try:
        native_token = child_network.get("nativeToken")
        if not native_token or native_token == ADDRESS_ZERO:
            return 18

        token = load_contract(
            provider=parent_provider,
            contract_name="ERC20",
            address=native_token,
        )
        return token.functions.decimals().call()
    except Exception as e:
        raise ArbSdkError(f"Failed to get native token decimals: {str(e)}") from e


def scale_from_18_decimals_to_native_token_decimals(amount: int, decimals: int) -> int:
    """
    Scale an amount from 18 decimals to native token decimals.

    :param amount: The integer to scale (assumes 18 decimals).
    :param decimals: The chain's native token decimals.
    :return: Scaled integer.
    """
    if decimals == 18:
        return amount

    if decimals < 18:
        # divide
        factor = 10 ** (18 - decimals)
        scaled = amount // factor
        # Round up if dividing was not exact
        if scaled * factor < amount:
            scaled += 1
        return scaled
    else:
        # multiply
        factor = 10 ** (decimals - 18)
        return amount * factor


def scale_from_native_token_decimals_to_18_decimals(amount: int, decimals: int) -> int:
    """
    Scale an amount from native token decimals to 18 decimals.

    Args:
        amount: Amount in native token decimals
        decimals: Current number of decimals

    Returns:
        Scaled amount with 18 decimals

    Example:
        >>> # Convert from 6 decimals to 18 decimals
        >>> eth_amount = scale_from_native_token_decimals_to_18_decimals(
        ...     1_000_000,  # 1.0 in 6 decimals
        ...     6
        ... )
    """
    if decimals < 18:
        return amount * (10 ** (18 - decimals))
    elif decimals > 18:
        return amount // (10 ** (decimals - 18))
    else:
        return amount
