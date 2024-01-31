from web3 import Web3
from web3.types import TxReceipt
# from decimal import Decimal
from typing import List, Optional, Any, Callable
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils, 
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.constants import NODE_INTERFACE_ADDRESS
from src.lib.utils.helper import load_contract
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.message.l2_to_l1_message import L2ToL1Message
from src.lib.data_entities.event import parse_typed_logs


class RedeemTransaction:
    def __init__(self, transaction, provider):
        self.transaction = transaction
        self.provider = provider

    async def wait(self):
        # Wait for the transaction to be mined
        # return await self.web3.eth.wait_for_transaction_receipt(
        #     self.transaction.transaction_hash
        # )
        return self.transaction

    async def wait_for_redeem(self):
        # rec = await self.wait()
        l2_receipt = L2TransactionReceipt(self.transaction)

        redeem_scheduled_events = l2_receipt.get_redeem_scheduled_events(self.provider)

        if len(redeem_scheduled_events) != 1:
            raise ArbSdkError(
                f"Transaction is not a redeem transaction: {self.transaction.transactionHash}"
            )

        return self.provider.eth.get_transaction_receipt(
            redeem_scheduled_events[0]["retryTxHash"]
        )


class L2TransactionReceipt:
    def __init__(self, tx: TxReceipt):
        self.to = tx.get("to")
        self.from_ = tx.get("from")
        self.contract_address = tx.get("contractAddress")
        self.transaction_index = tx.get("transactionIndex")
        self.root = tx.get("root")
        self.gas_used = tx.get("gasUsed")
        self.logs_bloom = tx.get("logsBloom")
        self.block_hash = tx.get("blockHash")
        self.transaction_hash = tx.get("transactionHash")
        self.logs = tx.get("logs")
        self.block_number = tx.get("blockNumber")
        self.confirmations = tx.get("confirmations")
        self.cumulative_gas_used = tx.get("cumulativeGasUsed")
        self.effective_gas_price = tx.get("effectiveGasPrice")
        self.byzantium = tx.get("byzantium")
        self.type = tx.get("type")
        self.status = tx.get("status")

    def get_l2_to_l1_events(self, provider):
        classic_logs = parse_typed_logs( provider,
            "ArbSys", self.logs, "L2ToL1Transaction"
        )
    
        nitro_logs = parse_typed_logs(provider, 'ArbSys', self.logs, 'L2ToL1Tx')
        
        return [*classic_logs, *nitro_logs]


    def get_redeem_scheduled_events(self, provider):
        return parse_typed_logs( provider,
            "ArbRetryableTx", self.logs, "RedeemScheduled"
        )

    async def get_l2_to_l1_messages(self, l1_signer_or_provider):
        provider = SignerProviderUtils.get_provider(l1_signer_or_provider)
        if not provider:
            raise ArbSdkError("Signer not connected to provider.")
        
        return [
            L2ToL1Message.from_event(l1_signer_or_provider, log)
            for log in self.get_l2_to_l1_events(provider)
        ]

    def get_batch_confirmations(self, provider: Web3) -> int:
        node_interface = load_contract(
            contract_name="NodeInterface", address=NODE_INTERFACE_ADDRESS, provider=provider, is_classic=False
        ) # also available in classic!
        return node_interface.functions.getL1Confirmations(self.block_hash).call()

    async def get_batch_number(self, l2_provider) -> int:
        arb_provider = ArbitrumProvider(l2_provider)
        node_interface = load_contract(
            contract_name="NodeInterface", address=NODE_INTERFACE_ADDRESS, provider=l2_provider, is_classic=False
        ) # also available in classic
        rec = await arb_provider.get_transaction_receipt(self.transaction_hash)

        if rec is None:
            raise ArbSdkError("No receipt available for current transaction")

        return node_interface.functions.findBatchContainingBlock(rec.blockNumber).call()

    async def is_data_available(
        self, provider: Web3, confirmations: int = 10
    ) -> bool:
        batch_confirmations = self.get_batch_confirmations(provider)
        return batch_confirmations > confirmations

    @staticmethod
    def monkey_patch_wait(contract_transaction):
        # original_wait = contract_transaction.wait

        # async def patched_wait(_confirmations: Optional[int] = None):
        #     result = await original_wait()
        #     return L2TransactionReceipt(result)

        # contract_transaction.wait = patched_wait
        print('tx', contract_transaction)
        return L2TransactionReceipt(contract_transaction)
        # return contract_transaction
    
    @staticmethod
    def to_redeem_transaction(redeem_tx, web3_instance):
        return RedeemTransaction(redeem_tx, web3_instance)
