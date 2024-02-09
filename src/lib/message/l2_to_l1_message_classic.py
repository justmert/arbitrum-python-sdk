import asyncio

from src.lib.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import L2ToL1MessageStatus
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import load_contract
from src.lib.utils.lib import is_defined


class MessageBatchProofInfo:
    def __init__(
        self,
        proof,
        path,
        l2_sender,
        l1_dest,
        l2_block,
        l1_block,
        timestamp,
        amount,
        calldata_for_l1,
    ):
        self.proof = proof
        self.path = path
        self.l2_sender = l2_sender
        self.l1_dest = l1_dest
        self.l2_block = l2_block
        self.l1_block = l1_block
        self.timestamp = timestamp
        self.amount = amount
        self.calldata_for_l1 = calldata_for_l1


class L2ToL1MessageClassic:
    def __init__(self, batch_number, index_in_batch):
        self.batch_number = batch_number
        self.index_in_batch = index_in_batch

    @staticmethod
    def from_batch_number(l1_signer_or_provider, batch_number, index_in_batch, l1_provider=None):
        if SignerProviderUtils.is_signer(l1_signer_or_provider):
            return L2ToL1MessageWriterClassic(l1_signer_or_provider, batch_number, index_in_batch, l1_provider)
        else:
            return L2ToL1MessageReaderClassic(l1_signer_or_provider, batch_number, index_in_batch)

    @staticmethod
    async def get_l2_to_l1_events(
        l2_provider,
        filter,
        batch_number=None,
        destination=None,
        unique_id=None,
        index_in_batch=None,
    ):
        event_fetcher = EventFetcher(l2_provider)

        argument_filters = {}
        if batch_number:
            argument_filters["batchNumber"] = batch_number
        if destination:
            argument_filters["destination"] = destination
        if unique_id:
            argument_filters["uniqueId"] = unique_id

        events = [
            {**l.event, "transactionHash": l.transactionHash}
            for l in await event_fetcher.get_events(
                contract_factory="ArbSys",
                event_name="L2ToL1Transaction",
                argument_filters=argument_filters,
                filter={
                    "fromBlock": filter["fromBlock"],
                    "toBlock": filter["toBlock"],
                    "address": ARB_SYS_ADDRESS,
                    **filter,
                },
                is_classic=False,
            )
        ]

        if index_in_batch is not None:
            index_items = [event for event in events if event.args.indexInBatch == index_in_batch]
            if index_items:
                raise ArbSdkError("More than one indexed item found in batch.")
            else:
                return []
        else:
            return events


class L2ToL1MessageReaderClassic(L2ToL1MessageClassic):
    def __init__(self, l1_provider, batch_number, index_in_batch):
        super().__init__(batch_number, index_in_batch)
        self.l1_provider = l1_provider
        self.outbox_address = None
        self.proof = None

    async def get_outbox_address(self, l2_provider, batch_number):
        if not is_defined(self.outbox_address):
            l2_network = get_l2_network(l2_provider)

            outboxes = (
                l2_network.eth_bridge.classic_outboxes.items()
                if is_defined(l2_network.eth_bridge.classic_outboxes)
                else []
            )

            sorted_outboxes = sorted(outboxes, key=lambda x: x[1])

            res = next(
                (
                    item
                    for index, item in enumerate(sorted_outboxes)
                    if index == len(sorted_outboxes) - 1 or sorted_outboxes[index + 1][1] > batch_number
                ),
                None,
            )

            if not res:
                self.outbox_address = "0x0000000000000000000000000000000000000000"
            else:
                self.outbox_address = res[0]

        return self.outbox_address

    async def outbox_entry_exists(self, l2_provider):
        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=l2_provider,
            contract_name="Outbox",
            address=outbox_address,
            is_classic=False,
        )

        return outbox_contract.functions.outboxEntryExists(self.batch_number).call()

    @staticmethod
    async def try_get_proof_static(l2_provider, batch_number, index_in_batch):
        node_interface_contract = load_contract(
            provider=l2_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            is_classic=False,
        )
        try:
            return node_interface_contract.functions.legacyLookupMessageBatchProof(batch_number, index_in_batch).call()

        except Exception as e:
            if "batch doesn't exist" in str(e):
                return None
            else:
                raise e

    async def try_get_proof(self, l2_provider):
        if not is_defined(self.proof):
            self.proof = await L2ToL1MessageReaderClassic.try_get_proof_static(
                l2_provider, self.batch_number, self.index_in_batch
            )
        return self.proof

    async def has_executed(self, l2_provider):
        proof_info = await self.try_get_proof(l2_provider)
        if not is_defined(proof_info):
            return False

        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=self.l1_provider,
            contract_name="Outbox",
            address=outbox_address,
            is_classic=False,
        )

        try:
            transaction = outbox_contract.functions.executeTransaction(
                self.batch_number,
                proof_info.proof,
                proof_info.path,
                proof_info.l2_sender,
                proof_info.l1_dest,
                proof_info.l2_block,
                proof_info.l1_block,
                proof_info.timestamp,
                proof_info.amount,
                proof_info.calldata_for_l1,
            )

            self.l1_provider.send_transaction(transaction)
            return False
        except Exception as e:
            if "ALREADY_SPENT" in str(e):
                return True
            if "NO_OUTBOX_ENTRY" in str(e):
                return False
            raise e

    async def status(self, l2_provider):
        try:
            message_executed = await self.has_executed(l2_provider)
            if message_executed:
                return L2ToL1MessageStatus.EXECUTED

            outbox_entry_exists = await self.outbox_entry_exists(l2_provider)
            return L2ToL1MessageStatus.CONFIRMED if outbox_entry_exists else L2ToL1MessageStatus.UNCONFIRMED
        except Exception:
            return L2ToL1MessageStatus.UNCONFIRMED

    async def wait_until_outbox_entry_created(self, l2_provider, retry_delay=1000):
        exists = await self.outbox_entry_exists(l2_provider)
        if exists:
            return
        else:
            await asyncio.sleep(retry_delay / 1000)
            await self.wait_until_outbox_entry_created(l2_provider, retry_delay)

    async def get_first_executable_block(self, l2_provider):
        return None


class L2ToL1MessageWriterClassic(L2ToL1MessageReaderClassic):
    def __init__(self, l1_signer, batch_number, index_in_batch, l1_provider=None):
        super().__init__(
            l1_provider if l1_provider else l1_signer.provider,
            batch_number,
            index_in_batch,
        )
        self.l1_signer = l1_signer

    async def execute(self, l2_provider, overrides=None):
        status = await self.status(l2_provider)
        if status != L2ToL1MessageStatus.CONFIRMED:
            raise Exception(f"Cannot execute message. Status is: {status} but must be {L2ToL1MessageStatus.CONFIRMED}.")

        proof_info = await self.try_get_proof(l2_provider)
        if not is_defined(proof_info):
            raise Exception(f"Unexpected missing proof: {self.batch_number} {self.index_in_batch}")

        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=self.l1_provider,
            contract_name="Outbox",
            address=outbox_address,
            is_classic=False,
        )

        if overrides is None:
            overrides = {}

        if "from" not in overrides:
            overrides["from"] = self.l1_signer.account.address

        transaction_hash = outbox_contract.functions.executeTransaction(
            self.batch_number,
            proof_info.proof,
            proof_info.path,
            proof_info.l2_sender,
            proof_info.l1_dest,
            proof_info.l2_block,
            proof_info.l1_block,
            proof_info.timestamp,
            proof_info.amount,
            proof_info.calldata_for_l1,
        ).transact(overrides)

        tx_receipt = self.l1_signer.provider.eth.wait_for_transaction_receipt(transaction_hash)
        return tx_receipt
