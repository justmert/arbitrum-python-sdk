import json
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.contract import Contract
import asyncio
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from src.lib.utils.helper import load_contract
from src.lib.data_entities.signer_or_provider import SignerOrProvider, SignerProviderUtils
from src.lib.data_entities.message import L2ToL1MessageStatus


class MessageBatchProofInfo:
    def __init__(self, proof, path, l2_sender, l1_dest, l2_block, l1_block, timestamp, amount, calldata_for_l1):
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
        if  SignerProviderUtils.is_signer(l1_signer_or_provider):
            return L2ToL1MessageWriterClassic(l1_signer_or_provider, batch_number, index_in_batch, l1_provider)
        else:
            return L2ToL1MessageReaderClassic(l1_signer_or_provider, batch_number, index_in_batch)

    @staticmethod
    def get_l2_to_l1_events(l2_provider, from_block, to_block, batch_number=None, destination=None, unique_id=None, index_in_batch=None):
        # Load ABI files for ArbSys
        with open('src/abi/ArbSys.json') as f:
            arb_sys_abi = json.load(f)

        arb_sys_contract = l2_provider.eth.contract(address=Web3.to_checksum_address(ARB_SYS_ADDRESS), abi=arb_sys_abi)

        filters = {}
        if batch_number:
            filters['batchNumber'] = batch_number
        if destination:
            filters['destination'] = destination
        if unique_id:
            filters['uniqueId'] = unique_id

        events = arb_sys_contract.events.L2ToL1Transaction.createFilter(fromBlock=from_block, toBlock=to_block, argument_filters=filters).get_all_entries()

        if index_in_batch is not None:
            return [event for event in events if event.args.indexInBatch == index_in_batch]
        else:
            return events
        

class L2ToL1MessageReaderClassic(L2ToL1MessageClassic):
    def __init__(self, l1_provider, batch_number, index_in_batch):
        super().__init__(batch_number, index_in_batch)
        self.l1_provider = l1_provider
        self.outbox_address = None
        self.proof = None

    async def get_outbox_address(self, l2_provider, batch_number):
        if self.outbox_address is None:
            l2_network = get_l2_network(l2_provider)

            outboxes = l2_network.eth_bridge.classic_outboxes.items() if l2_network.eth_bridge.classic_outboxes else []
            sorted_outboxes = sorted(outboxes, key=lambda x: x[1])

            for outbox, activation_batch_number in sorted_outboxes:
                if activation_batch_number > batch_number:
                    self.outbox_address = outbox
                    break

            if self.outbox_address is None:
                self.outbox_address = '0x0000000000000000000000000000000000000000'

        return self.outbox_address

    async def outbox_entry_exists(self, l2_provider):
        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)
        with open('src/abi/Outbox.json') as f:
            outbox_abi = json.load(f)

        outbox_contract = l2_provider.eth.contract(address=outbox_address, abi=outbox_abi)
        return await outbox_contract.functions.outboxEntryExists(self.batch_number).call()

    @staticmethod
    async def try_get_proof_static(l2_provider, batch_number, index_in_batch):
        with open('src/abi/NodeInterface.json') as f:
            node_interface_abi = json.load(f)

        node_interface_contract = l2_provider.eth.contract(address=NODE_INTERFACE_ADDRESS, abi=node_interface_abi)
        try:
            return await node_interface_contract.functions.legacyLookupMessageBatchProof(batch_number, index_in_batch).call()
        except Exception as e:
            if "batch doesn't exist" in str(e):
                return None
            else:
                raise e


    async def try_get_proof(self, l2_provider):
        if self.proof is None:
            self.proof = await L2ToL1MessageReaderClassic.try_get_proof_static(l2_provider, self.batch_number, self.index_in_batch)
        return self.proof


    async def has_executed(self, l2_provider):
        proof_info = await self.try_get_proof(l2_provider)
        if proof_info is None:
            return False
        
        with open('src/abi/Outbox.json') as f:
            outbox_abi = json.load(f)

        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)
        outbox_contract = l2_provider.eth.contract(address=Web3.to_checksum_address(outbox_address), abi=outbox_abi)

        try:
            # Call the executeTransaction method statically to check if the message has already been executed
            await outbox_contract.functions.executeTransaction(
                self.batch_number,
                proof_info.proof,
                proof_info.path,
                proof_info.l2_sender,
                proof_info.l1_dest,
                proof_info.l2_block,
                proof_info.l1_block,
                proof_info.timestamp,
                proof_info.amount,
                proof_info.calldata_for_l1
            ).call()
            return False
        except Exception as e:
            if 'ALREADY_SPENT' in str(e):
                return True
            if 'NO_OUTBOX_ENTRY' in str(e):
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

    async def wait_until_outbox_entry_created(self, l2_provider, retry_delay=500):
        exists = await self.outbox_entry_exists(l2_provider)
        if exists:
            return
        else:
            await asyncio.sleep(retry_delay / 1000)  # Convert milliseconds to seconds
            await self.wait_until_outbox_entry_created(l2_provider, retry_delay)

    async def get_first_executable_block(self, l2_provider):
        # For classic l2toL1 messages, this method always returns None
        # as they can be executed in any block now.
        return None


class L2ToL1MessageWriterClassic(L2ToL1MessageReaderClassic):
    def __init__(self, l1_signer, batch_number, index_in_batch, l1_provider=None):
        super().__init__(l1_provider if l1_provider else l1_signer.provider, batch_number, index_in_batch)
        self.l1_signer = l1_signer

    async def execute(self, l2_provider, overrides=None):
        status = await self.status(l2_provider)
        if status != L2ToL1MessageStatus.CONFIRMED:
            raise Exception(f"Cannot execute message. Status is: {status} but must be {L2ToL1MessageStatus.CONFIRMED}.")

        proof_info = await self.try_get_proof(l2_provider)
        if proof_info is None:
            raise Exception(f"Unexpected missing proof: {self.batch_number} {self.index_in_batch}")


        with open('src/abi/Outbox.json') as f:
            outbox_abi = json.load(f)

        outbox_address = await self.get_outbox_address(l2_provider, self.batch_number)
        outbox_contract = l2_provider.eth.contract(address=Web3.to_checksum_address(outbox_address), abi=outbox_abi)

        # Execute the transaction
        # Note: The actual execution logic will depend on your setup and might need adjustments.
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
            overrides if overrides else {}
        )
        # Assuming `l1_signer` has the necessary methods to send a transaction.
        # This part may need to be adjusted based on how your Signer class is implemented.
        return await self.l1_signer.send_transaction(transaction)

