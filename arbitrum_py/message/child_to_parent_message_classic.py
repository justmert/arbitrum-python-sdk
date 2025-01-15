from typing import Any, Dict, List, Optional, Union

from eth_typing import BlockNumber, HexStr
from web3 import Web3
from web3.types import BlockIdentifier, TxParams, TxReceipt

from arbitrum_py.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.message import ChildToParentMessageStatus
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.utils.event_fetcher import EventFetcher
from arbitrum_py.utils.helper import load_contract
from arbitrum_py.utils.lib import is_defined, wait


class MessageBatchProofInfo:
    """
    Merkle proof info for verifying a message in the outbox entry on the parent chain.

    This class contains all the necessary information to verify and execute a message
    that was sent from a child chain to its parent chain. The proof information is
    used to validate the message's inclusion in the outbox entry.

    Attributes:
        proof: Merkle proof of message inclusion in outbox entry
        path: Merkle path to message
        l2_sender: Sender of original message (caller of ArbSys.sendTxToL1)
        l1_dest: Destination address for L1 contract call
        l2_block: L2 block number at which sendTxToL1 call was made
        l1_block: L1 block number at which sendTxToL1 call was made
        timestamp: L2 Timestamp at which sendTxToL1 call was made
        amount: Value in L1 message in wei
        calldata_for_l1: ABI-encoded L1 message data
    """

    def __init__(
        self,
        proof: List[str],
        path: int,
        l2_sender: str,
        l1_dest: str,
        l2_block: int,
        l1_block: int,
        timestamp: int,
        amount: int,
        calldata_for_l1: HexStr,
    ) -> None:
        """
        Initialize a message batch proof info object.

        Args:
            proof: Merkle proof of message inclusion in outbox entry
            path: Merkle path to message
            l2_sender: Sender of original message (caller of ArbSys.sendTxToL1)
            l1_dest: Destination address for L1 contract call
            l2_block: L2 block number at which sendTxToL1 call was made
            l1_block: L1 block number at which sendTxToL1 call was made
            timestamp: L2 Timestamp at which sendTxToL1 call was made
            amount: Value in L1 message in wei
            calldata_for_l1: ABI-encoded L1 message data
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

    This class provides core functionality for handling messages sent from a child
    chain to its parent chain in the Arbitrum Classic protocol. It supports both
    reading and writing operations through its subclasses.

    The class manages message batches and their indices, providing methods to track
    and verify message status across both chains.

    Attributes:
        batch_number: The number of the batch this message is part of
        index_in_batch: The index of this message in the batch
    """

    def __init__(self, batch_number: int, index_in_batch: int) -> None:
        """
        Initialize a Classic Child-to-Parent message handler.

        Args:
            batch_number: The number of the batch this message is part of
            index_in_batch: The index of this message in the batch
        """
        self.batch_number = batch_number
        self.index_in_batch = index_in_batch

    @staticmethod
    def from_batch_number(
        parent_signer_or_provider: Any,
        batch_number: int,
        index_in_batch: int,
        parent_provider: Optional[Web3] = None,
    ) -> Union["ChildToParentMessageReaderClassic", "ChildToParentMessageWriterClassic"]:
        """
        Create a new Classic Child-to-Parent message handler.

        This factory method creates either a reader or writer instance based on whether
        a signer or provider is supplied. The choice between reader and writer determines
        the available operations on the message.

        Args:
            parent_signer_or_provider: Signer or provider for the parent chain
            batch_number: The batch number containing the message
            index_in_batch: The index of the message within the batch
            parent_provider: Optional override for the provider

        Returns:
            Either a ChildToParentMessageReaderClassic for read-only operations or
            ChildToParentMessageWriterClassic for execution operations
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
        child_provider: Web3,
        filter: Dict[str, BlockIdentifier],
        batch_number: Optional[int] = None,
        destination: Optional[str] = None,
        unique_id: Optional[int] = None,
        index_in_batch: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get Child-to-Parent message events from the child chain.

        This method retrieves events that represent messages sent from the child
        chain to the parent chain within the specified block range. It supports
        filtering by various parameters to find specific messages.

        Args:
            child_provider: Web3 provider for the child chain
            filter: Block range filter with fromBlock and toBlock
            batch_number: Optional batch number to filter events
            destination: Optional destination address to filter events
            unique_id: Optional unique identifier to filter events
            index_in_batch: Optional index in batch to filter events

        Returns:
            List of event objects containing message information. Each event includes
            the event args plus transactionHash.
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
                "fromBlock": filter["fromBlock"],
                "toBlock": filter["toBlock"],
                "address": ARB_SYS_ADDRESS,
                **filter,
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

    This class provides methods to read and verify the status of messages sent from
    a child chain to its parent chain, without the ability to execute them. It is
    used for monitoring and verifying message status across chains.

    Attributes:
        parent_provider: The parent chain provider to query message state
        batch_number: The batch number for this message (inherited)
        index_in_batch: The index in the batch for this message (inherited)
        outbox_address: Cached outbox contract address
        proof: Cached message proof information
    """

    def __init__(self, parent_provider: Web3, batch_number: int, index_in_batch: int) -> None:
        """
        Initialize a Classic Child-to-Parent message reader.

        Args:
            parent_provider: Web3 provider for the parent chain
            batch_number: The batch number for this message
            index_in_batch: The index in the batch for this message
        """
        super().__init__(batch_number, index_in_batch)
        self.parent_provider = parent_provider
        self.outbox_address = None
        self.proof = None

    def get_outbox_address(self, child_provider: Web3, batch_number: int) -> str:
        """
        Get the correct outbox contract address for a given batch number.

        Classic Arbitrum had multiple outboxes; this method finds the correct outbox
        by comparing the activation batch number of outboxes. If the next outbox's
        activation batch is higher than the current batch number, the current outbox
        is the correct one.

        Args:
            child_provider: Web3 provider for the child chain
            batch_number: The batch number to find the outbox for

        Returns:
            The address of the correct outbox contract for this batch

        Raises:
            ArbSdkError: If no valid outbox is found for the batch number
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

    def outbox_entry_exists(self, child_provider: Web3) -> bool:
        """
        Check if the outbox entry for this batch exists on the parent chain.

        This method verifies whether the outbox entry for this message's batch
        has been created on the parent chain, which is necessary before the
        message can be executed.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            True if the outbox entry exists, False otherwise
        """
        outbox_address = self.get_outbox_address(child_provider, self.batch_number)

        outbox_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Outbox",
            address=outbox_address,
        )

        return outbox_contract.functions.outboxEntryExists(self.batch_number).call()

    @staticmethod
    def try_get_proof_static(
        child_provider: Web3, batch_number: int, index_in_batch: int
    ) -> Optional[MessageBatchProofInfo]:
        """
        Try to get the Merkle proof for a specific message.

        This static method attempts to retrieve the proof information for a message
        identified by its batch number and index. The proof is necessary for
        executing the message on the parent chain.

        Args:
            child_provider: Web3 provider for the child chain
            batch_number: The batch number containing the message
            index_in_batch: The index of the message within the batch

        Returns:
            MessageBatchProofInfo if the proof exists, None if the batch is not
            yet created or the proof cannot be retrieved

        Raises:
            ArbSdkError: If there is an error retrieving the proof that is not
                        related to the batch not existing
        """
        node_interface_contract = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
        )
        try:
            return node_interface_contract.functions.legacyLookupMessageBatchProof(batch_number, index_in_batch).call()
        except Exception as e:
            if "batch doesn't exist" in str(e):
                return None
            raise e

    def try_get_proof(self, child_provider: Web3) -> Optional[MessageBatchProofInfo]:
        """
        Try to get the proof for this message.

        This method attempts to retrieve and cache the proof information for this
        message. If the proof has already been cached, it returns the cached version.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            MessageBatchProofInfo if the proof exists and can be retrieved,
            None otherwise
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

    def has_executed(self, child_provider: Web3) -> bool:
        """
        Check if this message has been executed on the parent chain.

        This method verifies whether the message has already been executed by
        checking its status on the parent chain. A message can only be executed
        once.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            True if the message has been executed, False otherwise

        Raises:
            ArbSdkError: If there is an error checking the execution status
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

    def status(self, child_provider: Web3) -> ChildToParentMessageStatus:
        """
        Get the current status of this message.

        This method checks the current state of the message and returns its status:
        - UNCONFIRMED: The outbox entry has not been created yet
        - CONFIRMED: The outbox entry exists but the message hasn't been executed
        - EXECUTED: The message has been successfully executed

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            ChildToParentMessageStatus indicating the current state of the message
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
        child_provider: Web3,
        retry_delay_ms: int = 500,
    ) -> ChildToParentMessageStatus:
        """
        Wait for the outbox entry to be created on the parent chain.

        This method continuously checks for the existence of the outbox entry,
        waiting between attempts. It will return once the entry is created or
        if the message has already been executed.

        Args:
            child_provider: Web3 provider for the child chain
            retry_delay_ms: Milliseconds to wait between checks (default: 500)

        Returns:
            ChildToParentMessageStatus of either CONFIRMED or EXECUTED
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

    def get_first_executable_block(self, child_provider: Web3) -> Optional[BlockNumber]:
        """
        Get the first block number where this message can be executed.

        In Classic Arbitrum, messages can be executed in any block after the outbox
        entry is created, so this method always returns None.

        Args:
            child_provider: Web3 provider for the child chain

        Returns:
            None, as Classic messages can be executed in any block after confirmation
        """
        return None


class ChildToParentMessageWriterClassic(ChildToParentMessageReaderClassic):
    """
    Write access for a Classic Child-to-Parent message.

    This class extends ChildToParentMessageReaderClassic to add execution capabilities
    for messages sent from a child chain to its parent chain. It provides methods to
    execute messages once they are confirmed on the parent chain.

    Attributes:
        parent_signer: The signer to use for executing transactions
        parent_provider: The parent chain provider (inherited)
        batch_number: The batch number for this message (inherited)
        index_in_batch: The index in the batch for this message (inherited)
    """

    def __init__(
        self,
        parent_signer: Any,
        batch_number: int,
        index_in_batch: int,
        parent_provider: Optional[Web3] = None,
    ) -> None:
        """
        Initialize a Classic Child-to-Parent message writer.

        Args:
            parent_signer: Signer for the parent chain transactions
            batch_number: The batch number for this message
            index_in_batch: The index in the batch for this message
            parent_provider: Optional override for the parent's provider
        """
        super().__init__(
            parent_provider if parent_provider else parent_signer.provider,
            batch_number,
            index_in_batch,
        )
        self.parent_signer = parent_signer

    def execute(self, child_provider: Web3, overrides: Optional[TxParams] = None) -> TxReceipt:
        """
        Execute the Child-to-Parent message on the parent chain.

        This method executes a message that was previously sent from the child chain
        to the parent chain. The message must be in CONFIRMED status before it can
        be executed. The execution process involves:
        1. Verifying the message status
        2. Retrieving the outbox proof
        3. Submitting the executeTransaction to the outbox contract

        Args:
            child_provider: Web3 provider for the child chain
            overrides: Optional transaction parameter overrides. Common overrides include:
                      'from', 'gasLimit', 'maxFeePerGas', 'maxPriorityFeePerGas'

        Returns:
            Transaction receipt from the execution transaction

        Raises:
            ArbSdkError: If the message is not in CONFIRMED status or if the outbox
                        proof cannot be retrieved
        """
        current_status = self.status(child_provider)
        if current_status != ChildToParentMessageStatus.CONFIRMED:
            raise ArbSdkError(
                "Cannot execute message: outbox entry has not been created. "
                "The L2-to-L1 message is not yet confirmed. "
                "Wait for the outbox entry to be created before executing."
            )

        proof_info = self.try_get_proof(child_provider)
        if not proof_info:
            raise ArbSdkError(
                "Cannot execute message: failed to get outbox proof. "
                "This could mean the outbox entry has not been created yet."
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
        ).build_transaction(overrides)

        signed_tx = self.parent_signer.sign_transaction(tx)
        tx_hash = self.parent_provider.eth.send_raw_transaction(signed_tx.rawTransaction)

        # Wait for receipt
        receipt = self.parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        return receipt
