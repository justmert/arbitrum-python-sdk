import asyncio
from decimal import Decimal
from typing import Optional, Tuple, Union

from eth_typing import HexStr, BlockNumber
from web3 import Web3
from web3.constants import ADDRESS_ZERO
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt

from src.lib.data_entities.constants import ARB_SYS_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import ArbitrumNetwork, get_nitro_genesis_block
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import load_contract


def get_contract_instance(provider, contract_address, contract_abi):
    return provider.eth.contract(address=contract_address, abi=contract_abi)


async def get_base_fee(provider) -> int:
    """Get base fee from latest block"""
    latest_block = provider.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    if not base_fee:
        raise ArbSdkError(
            "Latest block did not contain base fee, ensure provider is connected to a network that supports EIP 1559."
        )
    return base_fee


async def wait(ms: int):
    """Wait for specified milliseconds"""
    await asyncio.sleep(ms / 1000)


async def get_transaction_receipt(
    provider,
    tx_hash: HexStr,
    confirmations: Optional[int] = None,
    timeout: Optional[int] = None
) -> Optional[TxReceipt]:
    """Get transaction receipt with optional confirmation and timeout"""
    if confirmations or timeout:
        try:
            receipt = provider.eth.wait_for_transaction_receipt(
                tx_hash, 
                timeout=timeout / 1000 if timeout else None
            )
            if confirmations:
                latest_block = provider.eth.block_number
                if latest_block - receipt.blockNumber < confirmations:
                    return None
            return receipt
        except TimeExhausted:
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


def is_defined(val) -> bool:
    """Check if value is defined"""
    return val is not None


async def is_arbitrum_chain(provider) -> bool:
    """Check if provider is connected to Arbitrum chain"""
    try:
        arb_sys_contract = load_contract(
            provider=provider,
            contract_name="ArbSys",
            address=ARB_SYS_ADDRESS,
            is_classic=False,
        )
        arb_sys_contract.functions.arbOSVersion().call()
        return True
    except Exception:
        return False


async def get_first_block_for_l1_block(
    arbitrum_provider,
    for_l1_block: int,
    allow_greater: bool = False,
    min_arbitrum_block: Optional[int] = None,
    max_arbitrum_block: Union[int, str] = "latest"
) -> Optional[int]:
    """
    Binary search to find first Arbitrum block for given L1 block number.
    
    Args:
        arbitrum_provider: The Arbitrum provider
        for_l1_block: Target L1 block number 
        allow_greater: Allow blocks with higher L1 number
        min_arbitrum_block: Minimum Arbitrum block to search from
        max_arbitrum_block: Maximum Arbitrum block to search to
        
    Returns:
        Matching block number or None
    """
    if not await is_arbitrum_chain(arbitrum_provider):
        return for_l1_block

    arb_provider = ArbitrumProvider(arbitrum_provider)
    current_arb_block = arb_provider.provider.eth.block_number
    arbitrum_chain_id = arb_provider.provider.eth.chain_id
    nitro_genesis_block = get_nitro_genesis_block(arbitrum_chain_id)

    async def get_l1_block(for_l2_block: int) -> int:
        block = await arb_provider.get_block(for_l2_block)
        return block.l1_block_number

    if not min_arbitrum_block:
        min_arbitrum_block = nitro_genesis_block

    if max_arbitrum_block == "latest":
        max_arbitrum_block = current_arb_block

    if min_arbitrum_block >= max_arbitrum_block:
        raise ValueError(
            f"'minArbitrumBlock' ({min_arbitrum_block}) must be lower than "
            f"'maxArbitrumBlock' ({max_arbitrum_block})."
        )

    if min_arbitrum_block < nitro_genesis_block:
        raise ValueError(
            f"'minArbitrumBlock' ({min_arbitrum_block}) cannot be below the Nitro genesis block, "
            f"which is {nitro_genesis_block} for the current network."
        )

    start = min_arbitrum_block
    end = max_arbitrum_block

    result_for_target_block = None  
    result_for_greater_block = None

    while start <= end:
        mid = start + (end - start) // 2
        l1_block = await get_l1_block(mid)

        if l1_block == for_l1_block:
            result_for_target_block = mid
            end = mid - 1
        elif l1_block < for_l1_block:
            start = mid + 1
        else:
            end = mid - 1
            if allow_greater:
                result_for_greater_block = mid

    return result_for_target_block or result_for_greater_block


async def get_block_ranges_for_l1_block(
    props: dict
) -> Tuple[Optional[int], Optional[int]]:
    """Get block ranges for L1 block"""
    arb_provider = ArbitrumProvider(props["arbitrum_provider"])
    current_arbitrum_block = await arb_provider.get_block_number()

    if not props.get("maxArbitrumBlock") or props["maxArbitrumBlock"] == "latest":
        props["maxArbitrumBlock"] = current_arbitrum_block

    results = await asyncio.gather(
        get_first_block_for_l1_block(
            **{**props, "allow_greater": False}
        ),
        get_first_block_for_l1_block(
            **{
                **props,
                "for_l1_block": props["for_l1_block"] + 1,
                "allow_greater": True
            }
        )
    )

    if not results[0]:
        return None, None

    if results[0] and results[1]:
        return results[0], results[1] - 1

    return results[0], props["maxArbitrumBlock"]


async def get_native_token_decimals(
    parent_provider,
    child_network: ArbitrumNetwork
) -> int:
    """Get decimals of native token"""
    native_token_address = child_network.native_token

    if not native_token_address or native_token_address == ADDRESS_ZERO:
        return 18

    native_token_contract = load_contract(
        provider=parent_provider,
        contract_name="ERC20",
        address=native_token_address,
        is_classic=True,
    )

    try:
        return native_token_contract.functions.decimals().call()
    except:
        return 0


def scale_from_18_decimals_to_native_token_decimals(
    amount: int,
    decimals: int
) -> int:
    """Scale amount from 18 decimals to native token decimals"""
    if decimals == 18:
        return amount

    if decimals < 18:
        scaled_amount = amount // (10 ** (18 - decimals))
        # Round up if necessary
        if scaled_amount * (10 ** (18 - decimals)) < amount:
            return scaled_amount + 1
        return scaled_amount

    # decimals > 18
    return amount * (10 ** (decimals - 18))


def scale_from_native_token_decimals_to_18_decimals(
    amount: int,
    decimals: int
) -> int:
    """Scale amount from native token decimals to 18 decimals"""
    if decimals < 18:
        return amount * (10 ** (18 - decimals))
    elif decimals > 18:
        return amount // (10 ** (decimals - 18))
    return amount