import json
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.contract import Contract

# Import or define ARB_SYS_ADDRESS and NODE_INTERFACE_ADDRESS constants
ARB_SYS_ADDRESS = '...'  # Replace with the actual address
NODE_INTERFACE_ADDRESS = '...'  # Replace with the actual address

# Load ABI files for ArbSys, Outbox, and NodeInterface contracts
with open('ArbSys__factory.json') as f:
    arb_sys_abi = json.load(f)
with open('Outbox__factory.json') as f:
    outbox_abi = json.load(f)
with open('NodeInterface__factory.json') as f:
    node_interface_abi = json.load(f)


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
        if isinstance(l1_signer_or_provider, Signer):
            return L2ToL1MessageWriterClassic(l1_signer_or_provider, batch_number, index_in_batch, l1_provider)
        else:
            return L2ToL1MessageReaderClassic(l1_signer_or_provider, batch_number, index_in_batch)

    @staticmethod
    def get_l2_to_l1_events(l2_provider, from_block, to_block, batch_number=None, destination=None, unique_id=None, index_in_batch=None):
        arb_sys_contract = l2_provider.eth.contract(address=Web3.toChecksumAddress(ARB_SYS_ADDRESS), abi=arb_sys_abi)
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
            l2_network = await get_l2_network(l2_provider)

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
        outbox_contract = l2_provider.eth.contract(address=outbox_address, abi=outbox_abi)
        return await outbox_contract.functions.outboxEntryExists(self.batch_number).call()

    @staticmethod
    async def try_get_proof(l2_provider, batch_number, index_in_batch):
        node_interface_contract = l2_provider.eth.contract(address=NODE_INTERFACE_ADDRESS, abi=node_interface_abi)
        try:
            return await node_interface_contract.functions.legacyLookupMessageBatchProof(batch_number, index_in_batch).call()
        except Exception as e:
            expected_error = "batch doesn't exist"
            actual_error = str(e)
            if expected_error in actual_error:
                return None
            else:
                raise e

    async def try_get_proof(self, l2_provider):
        if self.proof is None:
            self.proof = await L2ToL1MessageReaderClassic.try_get_proof(l2_provider, self.batch_number, self.index_in_batch)
        return self.proof


    # TO BE CONTINUE IN  