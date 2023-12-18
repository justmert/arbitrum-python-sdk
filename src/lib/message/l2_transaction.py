from web3 import Web3
from web3.types import TxReceipt, Log
from decimal import Decimal
from typing import List, Optional, Any, Callable
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
    SignerOrProvider,
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.utils.helper import load_contract
from src.lib.utils.arb_provider import ArbitrumProvider


class RedeemTransaction:
    def __init__(self, transaction, web3_instance):
        self.transaction = transaction
        self.web3 = web3_instance

    async def wait(self):
        # Wait for the transaction to be mined
        return await self.web3.eth.wait_for_transaction_receipt(
            self.transaction.transaction_hash
        )

    async def wait_for_redeem(self):
        rec = await self.wait()
        l2_receipt = L2TransactionReceipt(rec)

        redeem_scheduled_events = l2_receipt.get_redeem_scheduled_events()

        if len(redeem_scheduled_events) != 1:
            raise ArbSdkError(
                f"Transaction is not a redeem transaction: {rec.transactionHash}"
            )

        return await self.web3.eth.get_transaction_receipt(
            redeem_scheduled_events[0]["retryTxHash"]
        )


class L2TransactionReceipt:
    def __init__(self, tx: TxReceipt, event_fetcher: EventFetcher):
        self.to = tx["to"]
        self.from_ = tx["from"]
        self.contract_address = tx["contractAddress"]
        self.transaction_index = tx["transactionIndex"]
        self.root = tx.get("root")
        self.gas_used = Decimal(tx["gasUsed"])
        self.logs_bloom = tx["logsBloom"]
        self.block_hash = tx["blockHash"]
        self.transaction_hash = tx["transactionHash"]
        self.logs = tx["logs"]
        self.block_number = tx["blockNumber"]
        self.confirmations = tx["confirmations"]
        self.cumulative_gas_used = Decimal(tx["cumulativeGasUsed"])
        self.effective_gas_price = Decimal(tx["effectiveGasPrice"])
        self.byzantium = tx["byzantium"]
        self.type = tx["type"]
        self.status = tx.get("status")
        self.event_fetcher = event_fetcher

    def get_l2_to_l1_events(self):
        return self.event_fetcher.parse_typed_logs(
            "ArbSys", self.logs, "L2ToL1Transaction"
        )

    def get_redeem_scheduled_events(self):
        return self.event_fetcher.parse_typed_logs(
            "ArbRetryableTx", self.logs, "RedeemScheduled"
        )

    async def get_l2_to_l1_messages(self, l1_signer_or_provider):
        provider = SignerProviderUtils.get_provider(l1_signer_or_provider)
        if not provider:
            raise ArbSdkError("Signer not connected to provider.")

        return [
            L2ToL1Message.from_event(l1_signer_or_provider, log)
            for log in self.get_l2_to_l1_events()
        ]

    def get_batch_confirmations(self, web3_instance: Web3) -> int:
        node_interface = load_contract(
            "NodeInterface", NODE_INTERFACE_ADDRESS, web3_instance
        )
        return node_interface.functions.getL1Confirmations(self.block_hash).call()

    async def get_batch_number(self, web3_instance) -> int:
        arb_provider = ArbitrumProvider(web3_instance)
        node_interface = load_contract(
            "NodeInterface", NODE_INTERFACE_ADDRESS, arb_provider.w3
        )
        rec = await arb_provider.get_transaction_receipt(self.transaction_hash)

        if rec is None:
            raise ArbSdkError("No receipt available for current transaction")

        return node_interface.functions.findBatchContainingBlock(rec.blockNumber).call()

    async def is_data_available(
        self, web3_instance: Web3, confirmations: int = 10
    ) -> bool:
        batch_confirmations = self.get_batch_confirmations(web3_instance)
        return batch_confirmations > confirmations

    @staticmethod
    def monkey_patch_wait(contract_transaction):
        original_wait = contract_transaction.wait

        async def patched_wait(_confirmations: Optional[int] = None):
            result = await original_wait()
            return L2TransactionReceipt(result)

        contract_transaction.wait = patched_wait
        return contract_transaction

    @staticmethod
    def to_redeem_transaction(redeem_tx, web3_instance):
        return RedeemTransaction(redeem_tx, web3_instance)
