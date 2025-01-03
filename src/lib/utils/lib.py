import asyncio
from typing import Optional, Tuple, Union

from eth_typing import HexStr
from web3 import Web3
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt, BlockData

from src.lib.data_entities.constants import ARB_SYS_ADDRESS, ADDRESS_ZERO
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import ArbitrumNetwork, get_nitro_genesis_block
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import load_contract


async def wait(ms: int):
    """
    Wait for the specified number of milliseconds.

    :param ms: Time in milliseconds to sleep.
    """
    await asyncio.sleep(ms / 1000)


async def get_base_fee(provider: Web3) -> int:
    """
    Retrieves the base fee per gas from the latest block.
    
    :param provider: A Web3 provider connected to an EIP-1559 chain.
    :return: The base fee (integer).
    :raises ArbSdkError: If baseFeePerGas is not found (e.g., non-EIP1559 chain).
    """
    latest_block = provider.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")
    if base_fee is None:
        raise ArbSdkError(
            "Latest block did not contain base fee. Ensure provider is on EIP-1559-compatible chain."
        )
    return base_fee


async def get_transaction_receipt(
    provider: Web3,
    tx_hash: HexStr,
    confirmations: Optional[int] = None,
    timeout: Optional[int] = None
) -> Optional[TxReceipt]:
    """
    Retrieve a transaction receipt with optional confirmation count or timeout.

    :param provider: A Web3 provider instance.
    :param tx_hash: The transaction hash to fetch.
    :param confirmations: If provided, we only consider the tx as confirmed if the chain 
                          is that many blocks ahead of the tx's block.
    :param timeout: If provided, the maximum time in milliseconds to wait for confirmation.
    :return: The TxReceipt if found/confirmed, or None if it times out or not yet confirmed.
    """
    if confirmations or timeout:
        try:
            # Convert timeout from ms to seconds if provided
            actual_timeout_seconds = (timeout / 1000) if timeout else None

            receipt = provider.eth.wait_for_transaction_receipt(
                tx_hash, timeout=actual_timeout_seconds
            )
            if confirmations:
                latest_block_num = provider.eth.block_number
                if latest_block_num - receipt.blockNumber < confirmations:
                    # Not enough confirmations yet
                    return None
            return receipt
        except TimeExhausted:
            # Timed out
            return None
        except Exception as e:
            raise e
    else:
        try:
            return provider.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None
        except Exception as e:
            raise e


def is_defined(value) -> bool:
    """
    Check if the given value is not None.

    :param value: Any object
    :return: True if defined (not None), else False
    """
    return value is not None


async def is_arbitrum_chain(provider: Web3) -> bool:
    """
    Check if this provider is connected to an Arbitrum chain by calling arbOSVersion on ArbSys.

    :param provider: Web3 provider
    :return: True if Arbitrum chain (call succeeded), else False
    """
    arb_sys_contract = load_contract(
        provider=provider,
        contract_name="ArbSys",
        address=ARB_SYS_ADDRESS,
        is_classic=False,
    )
    try:
        arb_sys_contract.functions.arbOSVersion().call()
        return True
    except:
        return False


async def get_first_block_for_l1_block(
    arbitrum_provider: Web3,
    for_l1_block: int,
    allow_greater: bool = False,
    min_arbitrum_block: Optional[int] = None,
    max_arbitrum_block: Union[int, str] = "latest"
) -> Optional[int]:
    """
    Performs a binary search on the Arbitrum chain to find the first L2 block 
    that corresponds to the given L1 block number. 
    If `allow_greater` is True, then if we can't find an exact match, we can accept a block 
    with L1 blockNumber > for_l1_block.

    :param arbitrum_provider: Arbitrum chain provider (Web3).
    :param for_l1_block: The L1 block number we're searching for.
    :param allow_greater: Whether to accept a block with L1 blockNumber > for_l1_block if exact isn't found.
    :param min_arbitrum_block: The minimum Arbitrum block to consider in the search.
    :param max_arbitrum_block: The maximum Arbitrum block, or 'latest' as a string.
    :return: The L2 block number or None if not found.
    """
    # If it's not actually an Arbitrum chain, we just return for_l1_block as no search is needed
    if not await is_arbitrum_chain(arbitrum_provider):
        return for_l1_block

    arb_provider = ArbitrumProvider(arbitrum_provider)
    current_l2_block = arb_provider.provider.eth.block_number
    chain_id = arb_provider.provider.eth.chain_id
    nitro_genesis_block = get_nitro_genesis_block(chain_id)

    async def get_l1_block_number(l2_block_num: int) -> int:
        block = await arb_provider.get_block(l2_block_num)
        return block.l1_block_number

    if min_arbitrum_block is None:
        min_arbitrum_block = nitro_genesis_block
    if max_arbitrum_block == "latest":
        max_arbitrum_block = current_l2_block

    if min_arbitrum_block >= max_arbitrum_block:
        raise ValueError(
            f"minArbitrumBlock ({min_arbitrum_block}) must be below maxArbitrumBlock ({max_arbitrum_block})."
        )
    if min_arbitrum_block < nitro_genesis_block:
        raise ValueError(
            f"minArbitrumBlock ({min_arbitrum_block}) below the Nitro genesis block: {nitro_genesis_block}."
        )

    start = min_arbitrum_block
    end = max_arbitrum_block
    result_for_target = None
    result_for_greater = None

    while start <= end:
        mid = start + (end - start) // 2
        l1_block_of_mid = await get_l1_block_number(mid)

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


async def get_block_ranges_for_l1_block(props: dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns a [startBlock, endBlock] range in the Arbitrum chain for the given L1 block.
    If a start or end can't be found, we return (None, None).

    :param props: 
        {
          "arbitrum_provider": Web3,
          "for_l1_block": number,
          "allow_greater": bool,
          "min_arbitrum_block": int,
          "max_arbitrum_block": int or 'latest'
        }
    :return: A tuple (startBlock, endBlock) if found, else (None, None).
    """
    arb_provider = ArbitrumProvider(props["arbitrum_provider"])
    current_l2_block = arb_provider.provider.eth.block_number

    if not props.get("maxArbitrumBlock") or props["maxArbitrumBlock"] == "latest":
        props["maxArbitrumBlock"] = current_l2_block

    # Search for the exact or earliest L2 block that has L1 block == for_l1_block
    # And also search for the earliest L2 block that has L1 block > for_l1_block
    # Then subtract 1 from that to get the end range
    results = await asyncio.gather(
        get_first_block_for_l1_block(
            props["arbitrum_provider"],
            props["for_l1_block"],
            allow_greater=False,
            min_arbitrum_block=props.get("min_arbitrum_block"),
            max_arbitrum_block=props["maxArbitrumBlock"],
        ),
        get_first_block_for_l1_block(
            props["arbitrum_provider"],
            props["for_l1_block"] + 1,
            allow_greater=True,
            min_arbitrum_block=props.get("min_arbitrum_block"),
            max_arbitrum_block=props["maxArbitrumBlock"],
        )
    )

    start_block, block_after_end = results

    if not start_block:
        return None, None

    if start_block and block_after_end:
        return start_block, block_after_end - 1

    return start_block, props["maxArbitrumBlock"]


async def get_native_token_decimals(parent_provider: Web3, child_network: ArbitrumNetwork) -> int:
    """
    Returns the decimals for the chain's native token, or 18 if it's ETH or zero address.

    :param parent_provider: Web3 provider for the parent chain
    :param child_network: The ArbitrumNetwork config
    :return: The decimals for the native token
    """
    native_token_address = child_network.native_token
    if not native_token_address or native_token_address == ADDRESS_ZERO:
        return 18

    # Load the token
    token_contract = load_contract(
        provider=parent_provider,
        contract_name="ERC20",
        address=native_token_address,
        is_classic=True,
    )
    try:
        return token_contract.functions.decimals().call()
    except:
        # If the call fails
        return 0


def scale_from_18_decimals_to_native_token_decimals(amount: int, decimals: int) -> int:
    """
    Scale an integer `amount` from 18 decimals to the chain's native token decimals.

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
    Scale an integer `amount` from the chain's native token decimals back to 18 decimals.

    :param amount: The integer to scale
    :param decimals: The chain's native token decimals
    :return: An integer scaled to 18 decimals
    """
    if decimals < 18:
        return amount * (10 ** (18 - decimals))
    elif decimals > 18:
        return amount // (10 ** (decimals - 18))
    else:
        return amount
