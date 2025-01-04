from typing import List, Optional, Any, Dict

from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.event import parse_typed_logs
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.child_to_parent_message import ChildToParentMessage
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import CaseDict, load_contract


class RedeemTransaction:
    """A redeemable transaction with wait functionality"""
    def __init__(self, transaction, child_provider):
        self.transaction = transaction
        self.child_provider = child_provider

    async def wait(self):
        """Wait for transaction confirmation"""
        return self.transaction

    async def wait_for_redeem(self):
        """Wait for redeem completion"""
        child_receipt = ChildTransactionReceipt(self.transaction)
        redeem_scheduled_events = child_receipt.get_redeem_scheduled_events(
            self.child_provider
        )

        if len(redeem_scheduled_events) != 1:
            raise ArbSdkError(
                f"Transaction is not a redeem transaction: {self.transaction.transactionHash}"
            )

        return self.child_provider.eth.get_transaction_receipt(
            redeem_scheduled_events[0]["retryTxHash"]
        )


class ChildTransactionReceipt(CaseDict):
    """Extension of transaction receipt with Arbitrum-specific functionality"""
    
    def __init__(self, tx: Dict[str, Any]):
        super().__init__({
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
        })

    def get_child_to_parent_events(self, provider) -> List[Dict[str, Any]]:
        """Get child-to-parent transaction events"""
        classic_logs = parse_typed_logs(
            provider=provider,
            contract_name="ArbSys",
            logs=self.logs,
            event_name="L2ToL1Transaction",
            
        )

        nitro_logs = parse_typed_logs(
            provider=provider,
            contract_name="ArbSys", 
            logs=self.logs,
            event_name="L2ToL1Tx",
            
        )

        return [*classic_logs, *nitro_logs]

    def get_redeem_scheduled_events(self, provider) -> List[Dict[str, Any]]:
        """Get redeem scheduled events"""
        return parse_typed_logs(
            provider=provider,
            contract_name="ArbRetryableTx",
            logs=self.logs,
            event_name="RedeemScheduled"
        )

    async def get_child_to_parent_messages(self, parent_signer_or_provider):
        """Get child-to-parent messages"""
        provider = SignerProviderUtils.get_provider(parent_signer_or_provider)
        if not provider:
            raise ArbSdkError("Signer not connected to provider.")

        return [
            ChildToParentMessage.from_event(parent_signer_or_provider, log)
            for log in self.get_child_to_parent_events(provider)
        ]

    def get_batch_confirmations(self, child_provider) -> int:
        """Get batch confirmations on parent chain"""
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=child_provider,
            
        )
        return node_interface.functions.getL1Confirmations(self.block_hash).call()

    async def get_batch_number(self, child_provider) -> int:
        """Get the batch number containing this transaction"""
        arb_provider = ArbitrumProvider(child_provider)
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=child_provider, 
            
        )

        receipt = await arb_provider.get_transaction_receipt(self.transaction_hash)
        if receipt is None:
            raise ArbSdkError("No receipt available for current transaction")

        return node_interface.functions.findBatchContainingBlock(
            receipt.blockNumber
        ).call()

    async def is_data_available(
        self, 
        child_provider,
        confirmations: int = 10
    ) -> bool:
        """
        Check if transaction data is available on parent chain
        
        Args:
            child_provider: Child chain provider 
            confirmations: Number of required confirmations
            
        Returns:
            bool: True if data is available
        """
        batch_confirmations = self.get_batch_confirmations(child_provider)
        return int(batch_confirmations) > confirmations

    @staticmethod 
    def monkey_patch_wait(contract_transaction):
        """Add wait functionality to contract transaction"""
        return ChildTransactionReceipt(contract_transaction)

    @staticmethod
    def to_redeem_transaction(redeem_tx, child_provider):
        """Convert to redeemable transaction"""
        return RedeemTransaction(redeem_tx, child_provider)


class ChildContractTransaction:
    """Base class for child chain contract transactions"""
    async def wait(self, confirmations: Optional[int] = None) -> ChildTransactionReceipt:
        """Wait for transaction confirmation"""
        raise NotImplementedError()