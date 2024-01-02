from web3.types import (
    BlockData as Web3Block,
)
from typing import Union
from eth_typing import HexStr
from web3 import Web3

class ArbBlockProps:
    def __init__(self, send_root: HexStr, send_count: Union[int, str], l1_block_number: int):
        """
        The properties specific to an Arbitrum block.

        :param send_root: The merkle root of the withdrawals tree.
        :param send_count: Cumulative number of withdrawals since genesis.
        :param l1_block_number: The L1 block number as seen from within this L2 block.
        """
        self.send_root = send_root
        self.send_count = Web3.toInt(send_count)  # Converts BigNumber equivalent to Python int
        self.l1BlockNumber = l1_block_number


class ArbBlock(ArbBlockProps, Web3Block):
    """
    The Arbitrum-specific block structure, extending standard Web3 block with Arbitrum properties.
    """
    pass


class ArbBlockWithTransactions(ArbBlockProps, Web3Block):
    """
    The Arbitrum-specific block with transactions structure, extending standard Web3 block with transactions and Arbitrum properties.
    """
    pass


class ArbTransactionReceipt():
    def __init__(self, l1_block_number: int, gas_used_for_l1: Union[int, str], **kwargs):
        """
        Eth transaction receipt with additional Arbitrum specific fields.

        :param l1_block_number: The L1 block number that would be used for block.number calls that occur within this transaction.
        :param gas_used_for_l1: Amount of gas spent on L1 computation in units of L2 gas.
        """
        super().__init__(**kwargs)
        self.l1_block_number = l1_block_number
        self.gas_used_for_l1 = Web3.toInt(gas_used_for_l1)  # Converts BigNumber equivalent to Python int
