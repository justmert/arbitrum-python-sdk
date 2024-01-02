import pytest
from web3 import Web3, HTTPProvider
from eth_typing import HexStr
from src.lib.utils.lib import get_block_ranges_for_l1_block, get_first_block_for_l1_block
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.data_entities.rpc import ArbBlock
import asyncio

class ValidationException(Exception):
    pass

# Configure the ArbitrumProvider with the given RPC provider
provider = Web3(HTTPProvider('https://arb1.arbitrum.io/rpc'))
provider.net.version
arb_provider = ArbitrumProvider(provider=provider)

@pytest.mark.asyncio
async def validate_l2_blocks(l2_blocks, l2_blocks_count: int, block_type: str = 'number'):
    if len(l2_blocks) != l2_blocks_count:
        raise ValidationException(f"Expected L2 block range to have the array length of {l2_blocks_count}, got {len(l2_blocks)}.")

    if block_type == 'number' and not all(isinstance(block, int) or block is None for block in l2_blocks):
        raise ValidationException(f"Expected all blocks to be of type {block_type}.")

    if block_type == 'undefined' and not all(block is None for block in l2_blocks):
        raise ValidationException(f"Expected all blocks to be of type {block_type}.")

    if block_type == 'undefined':
        return

    tasks = []
    for index, l2_block in enumerate(l2_blocks):
        if l2_block is None:
            raise ValidationException('L2 block is undefined.')

        is_start_block = index == 0
        tasks.append(arb_provider.get_block(l2_block))
        tasks.append(arb_provider.get_block(l2_block + (-1 if is_start_block else 1)))

    blocks = await asyncio.gather(*tasks)

    for i in range(0, len(blocks), 2):
        start_block, adjacent_block = blocks[i], blocks[i + 1]

        # Assuming that the block's l1BlockNumber attribute returns a comparable BigNumber
        # Replace with appropriate conversion if needed
        if start_block and adjacent_block:
            if is_start_block:
                condition = start_block.l1BlockNumber > adjacent_block.l1BlockNumber
                if not condition:
                    raise ValidationException("L2 start block is not the first block in range for L1 block.")
            else:  
                condition = start_block['l1BlockNumber'] < adjacent_block['l1BlockNumber']
                assert start_block['l1BlockNumber'] < adjacent_block['l1BlockNumber']
                if not condition:
                    raise ValidationException("L2 end block is not the last block in range for L1 block.")

@pytest.mark.asyncio
async def test_successfully_searches_for_an_l2_block_range():
    l2_blocks = await get_block_ranges_for_l1_block(arb_provider, 17926532, 121800000, 122000000)
    await validate_l2_blocks(l2_blocks, 2)

# @pytest.mark.asyncio
# async def test_fails_to_search_for_an_l2_block_range():
#     l2_blocks = await get_block_ranges_for_l1_block(arb_provider, 17926533, 121800000, 122000000)
#     await validate_l2_blocks(l2_blocks, 2, 'undefined')

# @pytest.mark.asyncio
# async def test_successfully_searches_for_the_first_l2_block():
#     l2_blocks = [await get_first_block_for_l1_block(arb_provider, 17926532, 121800000, 122000000)]
#     await validate_l2_blocks(l2_blocks, 1)

# @pytest.mark.asyncio
# async def test_fails_to_search_for_the_first_l2_block_without_allowGreater():
#     l2_blocks = [await get_first_block_for_l1_block(arb_provider, 17926533, 121800000, 122000000, allow_greater=False)]
#     await validate_l2_blocks(l2_blocks, 1, 'undefined')

# @pytest.mark.asyncio
# async def test_successfully_searches_for_the_first_l2_block_with_allowGreater():
#     l2_blocks = [await get_first_block_for_l1_block(arb_provider, 17926533, 121800000, 122000000, allow_greater=True)]
#     await validate_l2_blocks(l2_blocks, 1)
