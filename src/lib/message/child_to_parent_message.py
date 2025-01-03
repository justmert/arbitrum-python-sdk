import asyncio
from typing import Optional

from web3.providers import BaseProvider

import src.lib.message.child_to_parent_message_classic as classic
import src.lib.message.child_to_parent_message_nitro as nitro
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_arbitrum_network, get_nitro_genesis_block
from src.lib.data_entities.signer_or_provider import SignerProviderUtils


class ChildToParentMessage:
    @staticmethod
    def is_classic(event):
        return "indexInBatch" in event

    @staticmethod
    def from_event(parent_signer_or_provider, event, parent_provider: Optional[BaseProvider] = None):
        if SignerProviderUtils.is_signer(parent_signer_or_provider):
            return ChildToParentMessageWriter(parent_signer_or_provider, event, parent_provider)
        else:
            return ChildToParentMessageReader(parent_signer_or_provider, event)

    @staticmethod
    async def get_child_to_parent_events(
        child_provider,
        filter,
        position=None,
        destination=None,
        hash=None,
        index_in_batch=None,
    ):
        child_chain = get_arbitrum_network(child_provider)
        child_nitro_genesis_block = get_nitro_genesis_block(child_chain)

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
            "fromBlock": in_classic_range(filter["fromBlock"], child_nitro_genesis_block),
            "toBlock": in_classic_range(filter["toBlock"], child_nitro_genesis_block),
        }

        nitro_filter = {
            "fromBlock": in_nitro_range(filter["fromBlock"], child_nitro_genesis_block),
            "toBlock": in_nitro_range(filter["toBlock"], child_nitro_genesis_block),
        }

        log_queries = []
        if classic_filter["fromBlock"] != classic_filter["toBlock"]:
            log_queries.append(
                classic.ChildToParentMessageClassic.get_child_to_parent_events(
                    child_provider,
                    classic_filter,
                    position,
                    destination,
                    hash,
                    index_in_batch,
                )
            )

        if nitro_filter["fromBlock"] != nitro_filter["toBlock"]:
            log_queries.append(
                nitro.ChildToParentMessageNitro.get_child_to_parent_events(child_provider, nitro_filter, position, destination, hash)
            )

        results = await asyncio.gather(*log_queries)
        return [event for result in results for event in result]


class ChildToParentMessageReader(ChildToParentMessage):
    def __init__(self, parent_provider, event):
        super().__init__()
        if self.is_classic(event):
            self.classic_reader = classic.ChildToParentMessageReaderClassic(
                parent_provider, event["batchNumber"], event["indexInBatch"]
            )
            self.nitro_reader = None
        else:
            self.nitro_reader = nitro.ChildToParentMessageReaderNitro(parent_provider, event)
            self.classic_reader = None

    async def get_outbox_proof(self, child_provider):
        if self.nitro_reader:
            return await self.nitro_reader.get_outbox_proof(child_provider)
        else:
            return await self.classic_reader.try_get_proof(child_provider)

    async def status(self, child_provider):
        if self.nitro_reader:
            return await self.nitro_reader.status(child_provider)
        else:
            return await self.classic_reader.status(child_provider)

    async def wait_until_ready_to_execute(self, child_provider, retry_delay=500):
        if self.nitro_reader:
            await self.nitro_reader.wait_until_ready_to_execute(child_provider, retry_delay)
        else:
            await self.classic_reader.wait_until_outbox_entry_created(child_provider, retry_delay)

    async def get_first_executable_block(self, child_provider):
        if self.nitro_reader:
            return await self.nitro_reader.get_first_executable_block(child_provider)
        else:
            return await self.classic_reader.get_first_executable_block(child_provider)


class ChildToParentMessageWriter(ChildToParentMessageReader):
    def __init__(self, parent_signer, event, parent_provider=None):
        super().__init__(parent_provider or parent_signer.provider, event)
        if self.is_classic(event):
            self.classic_writer = classic.ChildToParentMessageWriterClassic(
                parent_signer, event["batchNumber"], event["indexInBatch"], parent_provider
            )
            self.nitro_writer = None
        else:
            self.nitro_writer = nitro.ChildToParentMessageWriterNitro(parent_signer, event, parent_provider)
            self.classic_writer = None

    async def execute(self, child_provider, overrides=None):
        if self.nitro_writer:
            return await self.nitro_writer.execute(child_provider, overrides)
        else:
            return await self.classic_writer.execute(child_provider, overrides)