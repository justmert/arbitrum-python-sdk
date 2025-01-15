from typing import Any, Dict, List, Optional

from web3.types import TxReceipt

from arbitrum_py.data_entities.constants import NODE_INTERFACE_ADDRESS
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.event import parse_typed_logs
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.message.child_to_parent_message import ChildToParentMessage
from arbitrum_py.utils.helper import CaseDict, load_contract


class RedeemTransaction:
    """A redeemable transaction with wait functionality.

    A transaction that can be redeemed on the Arbitrum chain.
    Provides methods to wait for both transaction confirmation and redeem completion.

    Args:
        transaction: The transaction object
        child_provider: The provider instance for child chain operations
    """

    def __init__(self, transaction: Dict[str, Any], child_provider: Any) -> None:
        self.transaction = transaction
        self.child_provider = child_provider

    def wait(self) -> Dict[str, Any]:
        """Wait for transaction confirmation.

        Returns:
            The transaction receipt
        """
        return self.transaction

    def wait_for_redeem(self) -> TxReceipt:
        """Wait for redeem completion and return the transaction receipt.

        This method waits for the redeem transaction to complete and returns the receipt
        of the redemption transaction.

        Returns:
            The transaction receipt of the redeem transaction

        Raises:
            ArbSdkError: If the transaction is not a valid redeem transaction
        """
        child_receipt = ChildTransactionReceipt(self.transaction)
        redeem_scheduled_events = child_receipt.get_redeem_scheduled_events()

        if len(redeem_scheduled_events) != 1:
            raise ArbSdkError(f"Transaction is not a redeem transaction: {self.transaction['transactionHash']}")

        return self.child_provider.eth.get_transaction_receipt(redeem_scheduled_events[0]["retryTxHash"])


class ChildTransactionReceipt(CaseDict):
    """Extension of transaction receipt with Arbitrum-specific functionality.

    This class extends the standard transaction receipt with additional methods
    specific to Arbitrum chain operations, such as handling child-to-parent messages
    and batch information.

    Args:
        tx: The transaction receipt dictionary
    """

    def __init__(self, tx: Dict[str, Any]) -> None:
        super().__init__(
            {
                "to": tx.get("to"),
                "from": tx.get("from"),
                "contractAddress": tx.get("contractAddress"),
                "transactionIndex": tx.get("transactionIndex"),
                "root": tx.get("root"),
                "gasUsed": tx.get("gasUsed"),
                "logsBloom": tx.get("logsBloom"),
                "blockHash": tx.get("blockHash"),
                "transactionHash": tx.get("transactionHash"),
                "logs": tx.get("logs"),
                "blockNumber": tx.get("blockNumber"),
                "confirmations": tx.get("confirmations"),
                "cumulativeGasUsed": tx.get("cumulativeGasUsed"),
                "effectiveGasPrice": tx.get("effectiveGasPrice"),
                "byzantium": tx.get("byzantium"),
                "type": tx.get("type"),
                "status": tx.get("status"),
            }
        )

    def get_child_to_parent_events(self) -> List[Dict[str, Any]]:
        """Get child-to-parent transaction events.

        Retrieves both classic and nitro L2-to-L1 transaction events from the logs.

        Returns:
            List of child-to-parent transaction events
        """
        classic_logs = parse_typed_logs(
            contract_name="ArbSys",
            logs=self.logs,
            event_name="L2ToL1Transaction",
        )

        nitro_logs = parse_typed_logs(
            contract_name="ArbSys",
            logs=self.logs,
            event_name="L2ToL1Tx",
        )

        return [*classic_logs, *nitro_logs]

    def get_redeem_scheduled_events(self) -> List[Dict[str, Any]]:
        """Get redeem scheduled events from transaction logs.

        Returns:
            List of redeem scheduled events
        """

        return parse_typed_logs(contract_name="ArbRetryableTx", logs=self.logs, event_name="RedeemScheduled")

    def get_child_to_parent_messages(self, parent_signer_or_provider: Any) -> List[ChildToParentMessage]:
        """Get child-to-parent messages from the transaction.

        Args:
            parent_signer_or_provider: The parent chain signer or provider

        Returns:
            List of child-to-parent messages

        Raises:
            ArbSdkError: If signer is not connected to a provider
        """
        provider = SignerProviderUtils.get_provider(parent_signer_or_provider)
        if not provider:
            raise ArbSdkError("Signer not connected to provider.")

        return [
            ChildToParentMessage.from_event(parent_signer_or_provider, log) for log in self.get_child_to_parent_events()
        ]

    def get_batch_confirmations(self, child_provider: Any) -> int:
        """Get batch confirmations on parent chain.

        Args:
            child_provider: The child chain provider

        Returns:
            Number of confirmations
        """
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=child_provider,
        )
        return node_interface.functions.getL1Confirmations(self.block_hash).call()

    def get_batch_number(self, child_provider: Any) -> int:
        """Get the batch number containing this transaction.

        Args:
            child_provider: The child chain provider

        Returns:
            Batch number
        """
        arb_provider = child_provider
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=arb_provider,
        )
        receipt = arb_provider.eth.get_transaction_receipt(self.transactionHash)
        if not receipt:
            raise ArbSdkError("Transaction receipt not found")

        return node_interface.functions.findBatchContainingBlock(receipt.blockNumber).call()

    def is_data_available(self, child_provider: Any, confirmations: int = 10) -> bool:
        """Check if transaction data is available on parent chain.

        Args:
            child_provider: The child chain provider
            confirmations: Number of required confirmations

        Returns:
            True if data is available
        """
        batch_confirmations = self.get_batch_confirmations(child_provider)
        return int(batch_confirmations) > confirmations

    @staticmethod
    def monkey_patch_wait(contract_transaction: Dict[str, Any]) -> "ChildTransactionReceipt":
        """Add wait functionality to contract transaction.

        Args:
            contract_transaction: The contract transaction

        Returns:
            The patched transaction receipt
        """
        return ChildTransactionReceipt(contract_transaction)

    @staticmethod
    def to_redeem_transaction(redeem_tx: Dict[str, Any], child_provider: Any) -> RedeemTransaction:
        """Convert to redeemable transaction.

        Args:
            redeem_tx: The redeem transaction
            child_provider: The child chain provider

        Returns:
            The redeem transaction
        """
        return RedeemTransaction(redeem_tx, child_provider)


class ChildContractTransaction:
    """Base class for child chain contract transactions."""

    def wait(self, confirmations: Optional[int] = None) -> ChildTransactionReceipt:
        """Wait for transaction confirmation.

        Args:
            confirmations: Number of confirmations to wait for

        Returns:
            The transaction receipt
        """
        raise NotImplementedError()
