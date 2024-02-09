import asyncio
from typing import Optional

from web3.providers import BaseProvider

import src.lib.message.l2_to_l1_message_classic as classic
import src.lib.message.l2_to_l1_message_nitro as nitro
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils


class L2ToL1Message:
    @staticmethod
    def is_classic(event):
        return "indexInBatch" in event

    @staticmethod
    def from_event(l1_signer_or_provider, event, l1_provider: Optional[BaseProvider] = None):
        if SignerProviderUtils.is_signer(l1_signer_or_provider):
            return L2ToL1MessageWriter(l1_signer_or_provider, event, l1_provider)
        else:
            return L2ToL1MessageReader(l1_signer_or_provider, event)

    @staticmethod
    async def get_l2_to_l1_events(
        l2_provider,
        filter,
        position=None,
        destination=None,
        hash=None,
        index_in_batch=None,
    ):
        l2_network = get_l2_network(l2_provider)

        def in_classic_range(block_tag, nitro_gen_block):
            if isinstance(block_tag, str):
                if block_tag == "earliest":
                    return 0
                elif block_tag in ["latest", "pending"]:
                    return nitro_gen_block
                else:
                    raise ArbSdkError(f"Unrecognised block tag. {block_tag}")
            return min(block_tag, nitro_gen_block)

        def in_nitro_range(block_tag, nitro_gen_block):
            if isinstance(block_tag, str):
                if block_tag == "earliest":
                    return nitro_gen_block
                elif block_tag in ["latest", "pending"]:
                    return block_tag
                else:
                    raise ArbSdkError(f"Unrecognised block tag. {block_tag}")
            return max(block_tag, nitro_gen_block)

        classic_filter = {
            "fromBlock": in_classic_range(filter["fromBlock"], l2_network.nitro_genesis_block),
            "toBlock": in_classic_range(filter["toBlock"], l2_network.nitro_genesis_block),
        }

        nitro_filter = {
            "fromBlock": in_nitro_range(filter["fromBlock"], l2_network.nitro_genesis_block),
            "toBlock": in_nitro_range(filter["toBlock"], l2_network.nitro_genesis_block),
        }

        log_queries = []
        if classic_filter["fromBlock"] != classic_filter["toBlock"]:
            log_queries.append(
                classic.L2ToL1MessageClassic.get_l2_to_l1_events(
                    l2_provider,
                    classic_filter,
                    position,
                    destination,
                    hash,
                    index_in_batch,
                )
            )

        if nitro_filter["fromBlock"] != nitro_filter["toBlock"]:
            log_queries.append(
                nitro.L2ToL1MessageNitro.get_l2_to_l1_events(l2_provider, nitro_filter, position, destination, hash)
            )

        results = await asyncio.gather(*log_queries)
        return [event for result in results for event in result]


class L2ToL1MessageReader(L2ToL1Message):
    def __init__(self, l1_provider, event):
        super().__init__()
        if self.is_classic(event):
            self.classic_reader = classic.L2ToL1MessageReaderClassic(
                l1_provider, event["batchNumber"], event["indexInBatch"]
            )
            self.nitro_reader = None
        else:
            self.nitro_reader = nitro.L2ToL1MessageReaderNitro(l1_provider, event)
            self.classic_reader = None

    async def get_outbox_proof(self, l2_provider):
        if self.nitro_reader:
            return await self.nitro_reader.get_outbox_proof(l2_provider)
        else:
            return await self.classic_reader.try_get_proof(l2_provider)

    async def status(self, l2_provider):
        if self.nitro_reader:
            return await self.nitro_reader.status(l2_provider)
        else:
            return await self.classic_reader.status(l2_provider)

    async def wait_until_ready_to_execute(self, l2_provider, retry_delay=500):
        if self.nitro_reader:
            await self.nitro_reader.wait_until_ready_to_execute(l2_provider, retry_delay)
        else:
            await self.classic_reader.wait_until_outbox_entry_created(l2_provider, retry_delay)

    async def get_first_executable_block(self, l2_provider):
        if self.nitro_reader:
            return await self.nitro_reader.get_first_executable_block(l2_provider)
        else:
            return await self.classic_reader.get_first_executable_block(l2_provider)


class L2ToL1MessageWriter(L2ToL1MessageReader):
    def __init__(self, l1_signer, event, l1_provider=None):
        super().__init__(l1_provider or l1_signer.provider, event)
        if self.is_classic(event):
            self.classic_writer = classic.L2ToL1MessageWriterClassic(
                l1_signer, event["batchNumber"], event["indexInBatch"], l1_provider
            )
            self.nitro_writer = None
        else:
            self.nitro_writer = nitro.L2ToL1MessageWriterNitro(l1_signer, event, l1_provider)
            self.classic_writer = None

    async def execute(self, l2_provider, overrides=None):
        if self.nitro_writer:
            return await self.nitro_writer.execute(l2_provider, overrides)
        else:
            return await self.classic_writer.execute(l2_provider, overrides)
