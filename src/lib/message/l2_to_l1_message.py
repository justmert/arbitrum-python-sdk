from typing import Union, Optional, Type
from web3.providers import BaseProvider
# from web3.contract import ContractTransaction

# Import necessary modules and classes
# from signer_or_provider import SignerOrProvider, is_signer
from src.lib.data_entities.signer_or_provider import SignerOrProvider, SignerProviderUtils
import classic
import nitro
# from arbsys import ClassicL2ToL1TransactionEvent, NitroL2ToL1TransactionEvent
from utils import is_defined
from message import L2ToL1MessageStatus
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.errors import ArbSdkError
import asyncio
from typing import Optional, List, Dict, Union
from web3 import Web3
from web3.types import BlockIdentifier

# Define L2ToL1TransactionEvent type
# L2ToL1TransactionEvent = Union[EventArgs[ClassicL2ToL1TransactionEvent], EventArgs[NitroL2ToL1TransactionEvent]]

# Base functionality for L2->L1 messages

# Define helper functions
def in_classic_range(block_tag: BlockIdentifier, nitro_gen_block: int):
    if isinstance(block_tag, str):
        if block_tag == 'earliest':
            return 0
        elif block_tag in ['latest', 'pending']:
            return nitro_gen_block
        else:
            raise ArbSdkError(f"Unrecognised block tag: {block_tag}")
    return min(block_tag, nitro_gen_block)

def in_nitro_range(block_tag: BlockIdentifier, nitro_gen_block: int):
    if isinstance(block_tag, str):
        if block_tag == 'earliest':
            return nitro_gen_block
        elif block_tag in ['latest', 'pending']:
            return block_tag
        else:
            raise ArbSdkError(f"Unrecognised block tag: {block_tag}")
    return max(block_tag, nitro_gen_block)


class L2ToL1Message:
    @staticmethod
    def is_classic(event) -> bool:
        return is_defined(getattr(event, 'index_in_batch', None))

    @staticmethod
    def from_event(l1_signer_or_provider: SignerOrProvider, event, l1_provider: Optional[BaseProvider] = None) -> Union['L2ToL1MessageReader', 'L2ToL1MessageWriter']:
        if SignerProviderUtils.is_signer(l1_signer_or_provider):
            return L2ToL1MessageWriter(l1_signer_or_provider, event, l1_provider)
        else:
            return L2ToL1MessageReader(l1_signer_or_provider, event)


    @staticmethod
    async def get_l2_to_l1_events(l2_provider: BaseProvider, filter: Dict[str, BlockIdentifier], position: Optional[int] = None, destination: Optional[str] = None, hash: Optional[int] = None, index_in_batch: Optional[int] = None) -> List[Dict[str, Union[int, str]]]:
        l2_network = await get_l2_network(l2_provider)

        classic_filter = {
            'fromBlock': in_classic_range(filter['fromBlock'], l2_network['nitro_genesis_block']),
            'toBlock': in_classic_range(filter['toBlock'], l2_network['nitro_genesis_block'])
        }

        nitro_filter = {
            'fromBlock': in_nitro_range(filter['fromBlock'], l2_network['nitro_genesis_block']),
            'toBlock': in_nitro_range(filter['toBlock'], l2_network['nitro_genesis_block'])
        }

        log_queries = []
        if classic_filter['fromBlock'] != classic_filter['toBlock']:
            log_queries.append(classic.get_l2_to_l1_events(l2_provider, classic_filter, position, destination, hash, index_in_batch))

        if nitro_filter['fromBlock'] != nitro_filter['toBlock']:
            log_queries.append(nitro.get_l2_to_l1_events(l2_provider, nitro_filter, position, destination, hash))

        results = await asyncio.gather(*log_queries)
        return [event for sublist in results for event in sublist]  # Flattening the list



class L2ToL1MessageReader(L2ToL1Message):
    def __init__(self, l1_provider: BaseProvider, event):
        super().__init__()
        if self.is_classic(event):
            self.classic_reader = classic.L2ToL1MessageReaderClassic(
                l1_provider, event['batchNumber'], event['indexInBatch']
            )
            self.nitro_reader = None
        else:
            self.nitro_reader = nitro.L2ToL1MessageReaderNitro(l1_provider, event)
            self.classic_reader = None

    async def get_outbox_proof(self, l2_provider: BaseProvider):
        if self.nitro_reader:
            return await self.nitro_reader.get_outbox_proof(l2_provider)
        else:
            return await self.classic_reader.try_get_proof(l2_provider)

    async def status(self, l2_provider: BaseProvider) -> L2ToL1MessageStatus:
        if self.nitro_reader:
            return await self.nitro_reader.status(l2_provider)
        else:
            return await self.classic_reader.status(l2_provider)

    async def wait_until_ready_to_execute(self, l2_provider: BaseProvider, retry_delay=500):
        if self.nitro_reader:
            await self.nitro_reader.wait_until_ready_to_execute(l2_provider, retry_delay)
        else:
            await self.classic_reader.wait_until_outbox_entry_created(l2_provider, retry_delay)


class L2ToL1MessageWriter(L2ToL1MessageReader):
    def __init__(self, l1_signer, event, l1_provider: Optional[BaseProvider] = None):
        super().__init__(l1_provider or l1_signer.provider, event)
        if self.is_classic(event):
            self.classic_writer = classic.L2ToL1MessageWriterClassic(
                l1_signer, event['batchNumber'], event['indexInBatch'], l1_provider
            )
            self.nitro_writer = None
        else:
            self.nitro_writer = nitro.L2ToL1MessageWriterNitro(l1_signer, event, l1_provider)
            self.classic_writer = None

    async def get_first_executable_block(self, l2_provider: BaseProvider):
        if self.nitro_writer:
            return await self.nitro_writer.get_first_executable_block(l2_provider)
        else:
            return await self.classic_writer.get_first_executable_block(l2_provider)

    async def execute(self, l2_provider: BaseProvider, overrides=None):
        if self.nitro_writer:
            return await self.nitro_writer.execute(l2_provider, overrides)
        else:
            return await self.classic_writer.execute(l2_provider, overrides)
