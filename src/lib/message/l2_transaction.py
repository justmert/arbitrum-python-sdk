from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.event import parse_typed_logs
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
)
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import CaseDict, load_contract


class RedeemTransaction:
    def __init__(self, transaction, l2_provider):
        self.transaction = transaction
        self.l2_provider = l2_provider

    async def wait(self):
        return self.transaction

    async def wait_for_redeem(self):
        l2_receipt = L2TransactionReceipt(self.transaction)

        redeem_scheduled_events = l2_receipt.get_redeem_scheduled_events(self.l2_provider)

        if len(redeem_scheduled_events) != 1:
            raise ArbSdkError(f"Transaction is not a redeem transaction: {self.transaction.transactionHash}")

        return self.l2_provider.eth.get_transaction_receipt(redeem_scheduled_events[0]["retryTxHash"])


class L2TransactionReceipt(CaseDict):
    def __init__(self, tx):
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

    def get_l2_to_l1_events(self, provider):
        classic_logs = parse_typed_logs(provider, "ArbSys", self.logs, "L2ToL1Transaction", is_classic=False)

        nitro_logs = parse_typed_logs(provider, "ArbSys", self.logs, "L2ToL1Tx", is_classic=False)

        return [*classic_logs, *nitro_logs]

    def get_redeem_scheduled_events(self, provider):
        return parse_typed_logs(provider, "ArbRetryableTx", self.logs, "RedeemScheduled")

    async def get_l2_to_l1_messages(self, l1_signer_or_provider):
        provider = SignerProviderUtils.get_provider(l1_signer_or_provider)
        if not provider:
            raise ArbSdkError("Signer not connected to provider.")

        return [L2ToL1Message.from_event(l1_signer_or_provider, log) for log in self.get_l2_to_l1_events(provider)]

    def get_batch_confirmations(self, l2_provider):
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=l2_provider,
            is_classic=False,
        )
        return node_interface.functions.getL1Confirmations(self.block_hash).call()

    async def get_batch_number(self, l2_provider):
        arb_provider = ArbitrumProvider(l2_provider)
        node_interface = load_contract(
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            provider=l2_provider,
            is_classic=False,
        )
        rec = await arb_provider.get_transaction_receipt(self.transaction_hash)

        if rec is None:
            raise ArbSdkError("No receipt available for current transaction")

        return node_interface.functions.findBatchContainingBlock(rec.blockNumber).call()

    async def is_data_available(self, l2_provider, confirmations=10):
        batch_confirmations = self.get_batch_confirmations(l2_provider)
        return int(batch_confirmations) > confirmations

    @staticmethod
    def monkey_patch_wait(contract_transaction):
        return L2TransactionReceipt(contract_transaction)

    @staticmethod
    def to_redeem_transaction(redeem_tx, l2_provider):
        return RedeemTransaction(redeem_tx, l2_provider)
