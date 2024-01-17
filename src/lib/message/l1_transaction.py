# Import necessary libraries
from web3 import Web3
from web3.contract import Contract
from web3.types import TxReceipt, TxParams
from typing import List, Optional, Tuple, Type
from decimal import Decimal
from eth_typing.evm import ChecksumAddress

# Assuming the existence of relevant modules and classes in the same project structure
from .l1_to_l2_message import (
    L1ToL2Message,
    L1ToL2MessageReaderClassic,
    L1ToL2MessageStatus,
    EthDepositMessage,
)


import json
from web3 import Web3
from web3.contract import Contract
from typing import Any, List, Optional, Type, Dict
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
)
from src.lib.data_entities.message import InboxMessageKind
from src.lib.message.message_data_parser import SubmitRetryableMessageDataParser
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.lib import is_defined


class L1TransactionReceipt():
    """
    A Python equivalent of the TypeScript L1TransactionReceipt class.
    """

    def __init__(self, tx, event_fetcher: EventFetcher = None):
        self.to: Optional[ChecksumAddress] = tx.get("to")
        self.from_: Optional[ChecksumAddress] = tx.get("from")
        self.contract_address: Optional[ChecksumAddress] = tx.get("contractAddress")
        self.transaction_index: int = tx.get("transactionIndex")
        self.root: Optional[str] = tx.get("root")
        self.gas_used: Decimal = tx.get("gasUsed")
        self.logs_bloom: str = tx.get("logsBloom")
        self.block_hash: str = tx.get("blockHash")
        self.transaction_hash: str = tx.get("transactionHash")
        self.logs = tx.get("logs")
        self.block_number: int = tx.get("blockNumber")
        self.confirmations: int = tx.get("confirmations")
        self.cumulative_gas_used: Decimal = tx.get("cumulativeGasUsed")
        self.effective_gas_price: Decimal = tx.get("effectiveGasPrice")
        self.byzantium: bool = tx.get("byzantium")
        self.type: int = tx.get("type")
        self.status: Optional[int] = tx.get("status")
        self.event_fetcher = event_fetcher


    async def get_l1_to_l2_messages_classic(
        self, l2_provider: Web3
    ) -> List[L1ToL2MessageReaderClassic]:
        network = get_l2_network(l2_provider)
        chain_id = network.chain_id
        is_classic = await self.is_classic(l2_provider)

        if not is_classic:
            raise Exception(
                "This method is only for classic transactions. Use 'getL1ToL2Messages' for nitro transactions."
            )

        message_nums = [
            msg["messageNum"] for msg in self.get_inbox_message_delivered_events()
        ]

        return [
            L1ToL2MessageReaderClassic(l2_provider, chain_id, message_num)
            for message_num in message_nums
        ]

    async def is_classic(self, l2_signer_or_provider) -> bool:
        provider = SignerProviderUtils.get_provider_or_throw(l2_signer_or_provider)
        network = get_l2_network(provider)
        return self.block_number < network.nitro_genesis_l1_block

    def get_message_delivered_events(self) -> List[Dict[str, Any]]:
        
        return  self.event_fetcher.parse_typed_logs(
            "Bridge", self.logs, "MessageDelivered"
        )
        

    def get_inbox_message_delivered_events(self) -> List[Dict[str, Any]]:
        return self.event_fetcher.parse_typed_logs(
            "Inbox", self.logs, "InboxMessageDelivered"
        )

    def get_message_events(self):
        bridge_messages = self.get_message_delivered_events()
        inbox_messages = self.get_inbox_message_delivered_events()

        if len(bridge_messages) != len(inbox_messages):
            raise ArbSdkError(
                f"Unexpected missing events. Inbox message count: {len(inbox_messages)} does not equal bridge message count: {len(bridge_messages)}."
            )

        messages = []
        for bm in bridge_messages:
            im = next(
                (i for i in inbox_messages if i["messageNum"] == bm["messageIndex"]),
                None,
            )
            if not im:
                raise ArbSdkError(
                    f"Unexpected missing event for message index: {bm['messageIndex']}."
                )

            messages.append(
                {
                    "inboxMessageEvent": im,
                    "bridgeMessageEvent": bm,
                }
            )

        return messages

    async def get_eth_deposits(self, l2_provider: Web3) -> List[EthDepositMessage]:
        messages = self.get_message_events()
        eth_deposit_messages = []

        for e in messages:
            if (
                e["bridgeMessageEvent"]["kind"]
                == InboxMessageKind.L1MessageType_ethDeposit.value
            ):
                eth_deposit_message = EthDepositMessage.from_event_components(
                    l2_provider,
                    e["inboxMessageEvent"]["messageNum"],
                    e["bridgeMessageEvent"]["sender"],
                    e["inboxMessageEvent"]["data"],
                )
                eth_deposit_messages.append(eth_deposit_message)

        return eth_deposit_messages

    async def get_l1_to_l2_messages(
        self, l2_signer_or_provider
    ):
        provider = SignerProviderUtils.get_provider_or_throw(l2_signer_or_provider)
        network = get_l2_network(provider)
        chain_id = network.chain_id
        is_classic = await self.is_classic(provider)

        if is_classic:
            raise Exception(
                "This method is only for nitro transactions. Use 'getL1ToL2MessagesClassic' for classic transactions."
            )

        events = self.get_message_events()
        return  [
            L1ToL2Message.from_event_components(
                l2_signer_or_provider,
                chain_id,
                event["bridgeMessageEvent"]["sender"],
                event["inboxMessageEvent"]["messageNum"],
                event["bridgeMessageEvent"]["baseFeeL1"],
                SubmitRetryableMessageDataParser.parse(
                    event["inboxMessageEvent"]["data"]
                ),
            )
            for event in events
            if event["bridgeMessageEvent"]["kind"]
            == InboxMessageKind.L1MessageType_submitRetryableTx.value
            and event["bridgeMessageEvent"]["inbox"].lower()
            == network.eth_bridge.inbox.lower()
        ]
        

    def get_token_deposit_events(self) -> List[Dict[str, Any]]:
        return self.event_fetcher.parse_typed_logs(
            "L1ERC20GatewayFactory", self.logs, "DepositInitiated"
        )

    @staticmethod
    def monkey_patch_wait(contract_transaction: Contract):
        original_wait = contract_transaction.wait

        async def patched_wait(
            confirmations: Optional[int] = None
        ) -> L1TransactionReceipt:
            result = await original_wait(confirmations)
            return L1TransactionReceipt(result)

        contract_transaction.wait = patched_wait
        return contract_transaction

    @staticmethod
    def monkey_patch_eth_deposit_wait(contract_transaction: Contract):
        original_wait = contract_transaction.wait

        async def patched_wait(
            confirmations: Optional[int] = None
        ) -> L1EthDepositTransactionReceipt:
            result = await original_wait(confirmations)
            return L1EthDepositTransactionReceipt(result)

        contract_transaction.wait = patched_wait
        return contract_transaction

    # @staticmethod
    # def monkey_patch_contract_call_wait(contract_transaction: Contract):
    #     original_wait = contract_transaction.wait

    #     async def patched_wait(
    #         confirmations: Optional[int] = None
    #     ) -> L1ContractCallTransactionReceipt:
    #         result = await original_wait(confirmations)
    #         return L1ContractCallTransactionReceipt(result)

    #     contract_transaction.wait = patched_wait
    #     return contract_transaction


    # web3.py handles the transaction receipt differently compared to ethers
    @staticmethod
    def monkey_patch_contract_call_wait(tx_receipt):
        # Your logic to modify the transaction receipt
        # Since the original_wait logic is specific to ethers.js,
        # you might need to adjust this part based on what you want to achieve in Python
        # ...

        return L1ContractCallTransactionReceipt(tx_receipt)  # Return the modified receipt


class L1EthDepositTransactionReceipt(L1TransactionReceipt):
    """
    L1TransactionReceipt with additional functionality for ETH deposit transactions.
    """

    async def wait_for_l2(
        self,
        l2_provider: Web3,
        confirmations: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        messages = await self.get_eth_deposits(l2_provider)
        if not messages:
            raise ArbSdkError("Unexpected missing Eth Deposit message.")

        message = messages[0]
        result = await message.wait(confirmations, timeout)

        return {
            "complete": is_defined(result),
            "l2_tx_receipt": result,
            "message": message,
        }


class L1ContractCallTransactionReceipt(L1TransactionReceipt):
    """
    L1TransactionReceipt with additional functionality for L2 contract call transactions.
    """

    async def wait_for_l2(
        self,
        l2_signer,
        l2_provider,
        confirmations: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        messages = await self.get_l1_to_l2_messages(l2_signer, l2_provider)
        if not messages:
            raise ArbSdkError("Unexpected missing L1ToL2 message.")

        message = messages[0]
        result = await message.wait_for_status(confirmations, timeout)

        return {
            "complete": result["status"] == L1ToL2MessageStatus.REDEEMED,
            **result,
            "message": message,
        }
