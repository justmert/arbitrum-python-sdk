from web3 import HTTPProvider, Web3
import pytest
from arbitrum_py.utils.arb_provider import ArbitrumProvider
from arbitrum_py.utils.lib import (
    get_block_ranges_for_l1_block,
    get_first_block_for_l1_block,
)


class ValidationException(Exception):
    pass


provider = Web3(HTTPProvider("https://arb1.arbitrum.io/rpc"))
arb_provider = provider


def validate_child_blocks(child_blocks, child_blocks_count, block_type="number"):
    """
    Validate child blocks for parent block

    :param child_blocks: List of child blocks to validate
    :param child_blocks_count: Expected number of child blocks
    :param block_type: Type of blocks ('number' or 'undefined')
    """
    if len(child_blocks) != child_blocks_count:
        raise ValidationException(
            f"Expected Child block range to have the array length of {child_blocks_count}, " f"got {len(child_blocks)}."
        )

    if block_type == "number" and not all(isinstance(block, int) or block is None for block in child_blocks):
        raise ValidationException("Expected all blocks to be integers or None.")

    if block_type == "undefined" and not all(block is None for block in child_blocks):
        raise ValidationException("Expected all blocks to be None when block type is 'undefined'.")

    if block_type == "undefined":
        return

    blocks = []
    for index, child_block in enumerate(child_blocks):
        if child_block is None:
            raise ValidationException("Child block is undefined.")

        is_start_block = index == 0

        # Get current block
        current_block = arb_provider.eth.get_block(child_block)
        blocks.append(current_block)

        # Get adjacent block (previous for start block, next for end block)
        adjacent_block = arb_provider.eth.get_block(child_block + (-1 if is_start_block else 1))
        blocks.append(adjacent_block)

    # Validate blocks
    for i in range(0, len(blocks), 2):
        current_block = blocks[i]
        adjacent_block = blocks[i + 1]

        if current_block is None or adjacent_block is None:
            continue

        current_block_number = int(current_block["l1BlockNumber"], 16)
        adjacent_block_number = int(adjacent_block["l1BlockNumber"], 16)

        is_start_block = i == 0

        if is_start_block:
            if not current_block_number > adjacent_block_number:
                raise ValidationException("Child start block is not the first block in range for parent block.")
        else:
            if not current_block_number < adjacent_block_number:
                raise ValidationException("Child end block is not the last block in range for parent block.")


def test_successfully_searches_for_child_block_range():
    """Test successful search for child block range"""
    child_blocks = get_block_ranges_for_l1_block(
        arbitrum_provider=arb_provider,
        for_l1_block=17926532,
        min_arbitrum_block=121800000,
        max_arbitrum_block=122000000,
    )
    validate_child_blocks(child_blocks, 2)


def test_fails_to_search_for_child_block_range():
    """Test failed search for child block range"""
    child_blocks = get_block_ranges_for_l1_block(
        arbitrum_provider=arb_provider,
        for_l1_block=17926533,
        min_arbitrum_block=121800000,
        max_arbitrum_block=122000000,
    )
    validate_child_blocks(child_blocks, 2, "undefined")


def test_successfully_searches_for_first_child_block():
    """Test successful search for first child block"""
    child_blocks = [
        get_first_block_for_l1_block(
            arbitrum_provider=arb_provider,
            for_l1_block=17926532,
            min_arbitrum_block=121800000,
            max_arbitrum_block=122000000,
        )
    ]
    validate_child_blocks(child_blocks, 1)


def test_fails_to_search_for_first_child_block_without_allow_greater():
    """Test failed search for first child block without allow_greater flag"""
    child_blocks = [
        get_first_block_for_l1_block(
            arbitrum_provider=arb_provider,
            for_l1_block=17926533,
            allow_greater=False,
            min_arbitrum_block=121800000,
            max_arbitrum_block=122000000,
        )
    ]
    validate_child_blocks(child_blocks, 1, "undefined")


def test_successfully_searches_for_first_child_block_with_allow_greater():
    """Test successful search for first child block with allow_greater flag"""
    child_blocks = [
        get_first_block_for_l1_block(
            arbitrum_provider=arb_provider,
            for_l1_block=17926533,
            allow_greater=True,
            # Expected result: 121907740. Narrows down the range to speed up the search.
            min_arbitrum_block=121800000,
            max_arbitrum_block=122000000,
        )
    ]
    validate_child_blocks(child_blocks, 1)
