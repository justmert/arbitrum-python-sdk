from eth_typing import BlockNumber
from web3.types import TxReceipt

from src.lib.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import ChildToParentMessageStatus
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import load_contract
from src.lib.utils.lib import is_defined, wait
from typing import List, Optional


class MessageBatchProofInfo:
    """
    Merkle proof info for verifying a message in the outbox entry on the parent chain.
    """

    def __init__(
        self,
        proof: List[str],
        path,
        l2_sender: str,
        l1_dest: str,
        l2_block,
        l1_block,
        timestamp,
        amount,
        calldata_for_l1: str,
    ):
        """
        :param proof: Merkle proof of message inclusion in outbox entry
        :param path: Merkle path to message
        :param l2_sender: Sender of original message (caller of ArbSys.sendTxToL1)
        :param l1_dest: Destination address for L1 contract call
        :param l2_block: L2 block number at which sendTxToL1 call was made
        :param l1_block: L1 block number at which sendTxToL1 call was made
        :param timestamp: L2 Timestamp at which sendTxToL1 call was made
        :param amount: Value in L1 message in wei
        :param calldata_for_l1: ABI-encoded L1 message data
        """
        self.proof = proof
        self.path = path
        self.l2_sender = l2_sender
        self.l1_dest = l1_dest
        self.l2_block = l2_block
        self.l1_block = l1_block
        self.timestamp = timestamp
        self.amount = amount
        self.calldata_for_l1 = calldata_for_l1


class ChildToParentMessageClassic:
    """
    Base class for Child-to-Parent messages on Arbitrum Classic networks.
    """

    def __init__(self, batch_number, index_in_batch):
        """
        :param batch_number: The number of the batch this message is part of
        :param index_in_batch: The index of this message in the batch
        """
        self.batch_number = batch_number
        self.index_in_batch = index_in_batch

    @staticmethod
    def from_batch_number(
        parent_signer_or_provider,
        batch_number,
        index_in_batch,
        parent_provider=None,
    ):
        """
        Instantiates a new ChildToParentMessageReaderClassic or ChildToParentMessageWriterClassic.

        :param parent_signer_or_provider: Signer or provider to be used for executing or reading
               the Child-to-Parent message on the parent chain.
        :param batch_number: The number of the batch containing the Child-to-Parent message.
        :param index_in_batch: The index of the Child-to-Parent message within the batch.
        :param parent_provider: Optional override for the provider attached to parent_signer_or_provider.
        :return: An instance of ChildToParentMessageReaderClassic or ChildToParentMessageWriterClassic
        """
        if SignerProviderUtils.is_signer(parent_signer_or_provider):
            return ChildToParentMessageWriterClassic(
                parent_signer_or_provider,
                batch_number,
                index_in_batch,
                parent_provider,
            )
        else:
            return ChildToParentMessageReaderClassic(
                parent_signer_or_provider,
                batch_number,
                index_in_batch,
            )

    @staticmethod
    def get_child_to_parent_events(
        child_provider,
        filter_dict: dict,
        batch_number=None,
        destination=None,
        unique_id=None,
        index_in_batch=None,
    ):
        """
        Fetches Child->Parent events from the child chain that match the provided filters.

        :param child_provider: A Web3 provider connected to the child chain
        :param filter_dict: Dictionary with 'fromBlock' and 'toBlock' for the event filter
        :param batch_number: (Optional) If provided, only match events from this batch number
        :param destination: (Optional) If provided, only match events with this L1 destination
        :param unique_id: (Optional) If provided, only match events with this unique ID
        :param index_in_batch: (Optional) If provided, only match a specific indexInBatch
        :return: A list of event objects, each containing the event args plus transactionHash
        """
        event_fetcher = EventFetcher(child_provider)

        # Build argument filters for L2ToL1Transaction
        argument_filters = {}
        if batch_number:
            argument_filters["batchNumber"] = batch_number
        if destination:
            argument_filters["destination"] = destination
        if unique_id:
            argument_filters["uniqueId"] = unique_id

        # The underlying event name on-chain is still "L2ToL1Transaction"
        events = []
        raw_events = event_fetcher.get_events(
            contract_factory="ArbSys",
            event_name="L2ToL1Transaction",
            argument_filters=argument_filters,
            filter={
                "fromBlock": filter_dict["fromBlock"],
                "toBlock": filter_dict["toBlock"],
                "address": ARB_SYS_ADDRESS,
                **filter_dict,
            },
            
        )
        for e in raw_events:
            event_data = {**e.event, "transactionHash": e.transactionHash}
            events.append(event_data)

        # If index_in_batch is specified, return exactly one match or none
        if index_in_batch is not None:
            matched = [ev for ev in events if ev["args"].indexInBatch == index_in_batch]
            if len(matched) == 1:
                return matched
            elif len(matched) > 1:
                raise ArbSdkError("More than one indexed item found in batch.")
            else:
                return []
        return events


class ChildToParentMessageReaderClassic(ChildToParentMessageClassic):
    """
    Read-only access for a Classic Child->Parent message.
    """

    def __init__(self, parent_provider, batch_number, index_in_batch):
        """
        :param parent_provider: The parent chain provider to query or read the state
        :param batch_number: The batch number for this message
        :param index_in_batch: The index in the batch for this message
        """
        super().__init__(batch_number, index_in_batch)
        self.parent_provider = parent_provider
        self.outbox_address = None
        self.proof = None

    def get_outbox_address(self, child_provider, batch_number):
        """
        Classic had multiple outboxes; find the correct outbox by comparing the activation batch
        number of the next outbox. If the next outbox's activation batch is higher than the
        provided batch_number, it means this outbox is the right one.
        If no outbox is found, use address zero.
        """
        if not is_defined(self.outbox_address):
            child_chain = get_arbitrum_network(child_provider)

            # classic_outboxes is a dict of form {outboxAddress: activationBatchNumber}
            outboxes = (
                child_chain.ethBridge.classicOutboxes.items()
                if is_defined(child_chain.ethBridge.classicOutboxes)
                else []
            )

            # Sort by activation batch number
            sorted_outboxes = sorted(outboxes, key=lambda x: x[1])

            # Find the outbox that applies for this batch_number
            res = None
            for idx, item in enumerate(sorted_outboxes):
                # If the next outbox doesn't exist or the next outbox's activation batch is bigger
                # than this batch_number, we've found our outbox
                if idx == len(sorted_outboxes) - 1 or sorted_outboxes[idx + 1][1] > batch_number:
                    res = item
                    break

            if not res:
                # No outbox found for this range
                self.outbox_address = "0x0000000000000000000000000000000000000000"
            else:
                self.outbox_address = res[0]

        return self.outbox_address

    def outbox_entry_exists(self, child_provider) -> bool:
        """
        Checks if the outbox entry for this batch_number has been created on the parent chain.
        """
        outbox_address = self.get_outbox_address(child_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Outbox",
            address=outbox_address,
            
        )

        return outbox_contract.functions.outboxEntryExists(self.batch_number).call()

    @staticmethod
    def try_get_proof_static(child_provider, batch_number, index_in_batch):
        """
        Fetches the Merkle proof (MessageBatchProofInfo) for the given message if it exists,
        otherwise returns None if the batch is not yet created.
        """
        node_interface_contract = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            
        )
        try:
            return node_interface_contract.functions.legacyLookupMessageBatchProof(
                batch_number, index_in_batch
            ).call()
        except Exception as e:
            if "batch doesn't exist" in str(e):
                return None
            raise e

    def try_get_proof(self, child_provider) -> Optional[MessageBatchProofInfo]:
        """
        Returns the proof for this message if it exists on-chain, otherwise None.
        """
        if not is_defined(self.proof):
            raw = ChildToParentMessageReaderClassic.try_get_proof_static(
                child_provider, self.batch_number, self.index_in_batch
            )
            if raw is not None:
                self.proof = MessageBatchProofInfo(
                    proof=raw[0],
                    path=raw[1],
                    l2_sender=raw[2],
                    l1_dest=raw[3],
                    l2_block=raw[4],
                    l1_block=raw[5],
                    timestamp=raw[6],
                    amount=raw[7],
                    calldata_for_l1=raw[8],
                )
        return self.proof

    def has_executed(self, child_provider) -> bool:
        """
        Checks whether this Child->Parent message has already been executed on the parent chain.
        """
        proof_info = self.try_get_proof(child_provider)
        if not is_defined(proof_info):
            return False

        outbox_address = self.get_outbox_address(child_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Outbox",
            address=outbox_address,
            
        )
        try:
            # Dry-run call to see if it reverts with ALREADY_SPENT or NO_OUTBOX_ENTRY
            tx = outbox_contract.functions.executeTransaction(
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
            _ = self.parent_provider.send_transaction(tx)  # dry-run
            return False
        except Exception as e:
            if "ALREADY_SPENT" in str(e):
                return True
            if "NO_OUTBOX_ENTRY" in str(e):
                return False
            raise e

    def status(self, child_provider) -> ChildToParentMessageStatus:
        """
        Get the status of this message: UNCONFIRMED, CONFIRMED, or EXECUTED.
        """
        try:
            executed = self.has_executed(child_provider)
            if executed:
                return ChildToParentMessageStatus.EXECUTED

            entry_exists = self.outbox_entry_exists(child_provider)
            if entry_exists:
                return ChildToParentMessageStatus.CONFIRMED
            else:
                return ChildToParentMessageStatus.UNCONFIRMED
        except Exception:
            return ChildToParentMessageStatus.UNCONFIRMED

    def wait_until_outbox_entry_created(
        self,
        child_provider,
        retry_delay_ms=500,
    ) -> ChildToParentMessageStatus:
        """
        Waits (possibly a very long time) until the outbox entry has been created. 
        Once created, returns either CONFIRMED or EXECUTED (if it was executed meanwhile).
        """
        entry_exists = self.outbox_entry_exists(child_provider)
        if entry_exists:
            # Outbox entry is created. Check if it's executed or just confirmed
            executed = self.has_executed(child_provider)
            return ChildToParentMessageStatus.EXECUTED if executed else ChildToParentMessageStatus.CONFIRMED
        else:
            # Not created yet, wait a bit and re-check
            wait(retry_delay_ms)
            return self.wait_until_outbox_entry_created(child_provider, retry_delay_ms)

    def get_first_executable_block(self, child_provider) -> Optional[BlockNumber]:
        """
        Classic outboxes can be executed in any block after the outbox entry is created,
        so we always return None for Classic.
        """
        return None


class ChildToParentMessageWriterClassic(ChildToParentMessageReaderClassic):
    """
    Read + Write access for a Classic Child->Parent message.
    """

    def __init__(
        self,
        parent_signer,
        batch_number,
        index_in_batch,
        parent_provider=None,
    ):
        """
        :param parent_signer: The signer to use when sending transactions on the parent chain
        :param batch_number: The batch number for this message
        :param index_in_batch: The index in the batch for this message
        :param parent_provider: Optional override for the parent's provider
        """
        super().__init__(
            parent_provider if parent_provider else parent_signer.provider,
            batch_number,
            index_in_batch,
        )
        self.parent_signer = parent_signer

    def execute(self, child_provider, overrides=None) -> TxReceipt:
        """
        Executes the Child->Parent message on the parent chain if the outbox entry has been created.
        Raises an exception if the message is not yet CONFIRMED.
        """
        current_status = self.status(child_provider)
        if current_status != ChildToParentMessageStatus.CONFIRMED:
            raise ArbSdkError(
                f"Cannot execute message. Status is: {current_status}, "
                f"but must be {ChildToParentMessageStatus.CONFIRMED}."
            )

        proof_info = self.try_get_proof(child_provider)
        if not is_defined(proof_info):
            raise ArbSdkError(
                f"Unexpected missing proof: batch {self.batch_number} index {self.index_in_batch}"
            )

        outbox_address = self.get_outbox_address(child_provider, self.batch_number)
        outbox_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Outbox",
            address=outbox_address,
            
        )

        if overrides is None:
            overrides = {}

        if "from" not in overrides:
            # Many Web3 libraries accept 'from' or 'sender' as part of transaction opts
            overrides["from"] = self.parent_signer.account.address

        # Submit the executeTransaction on the parent chain
        tx_hash = outbox_contract.functions.executeTransaction(
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

        # Wait for receipt
        receipt = self.parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        return receipt
