from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.event import parse_typed_logs
from src.lib.data_entities.message import InboxMessageKind
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import (
    SignerProviderUtils,
)
from src.lib.message.l1_to_l2_message import (
    EthDepositMessage,
    L1ToL2Message,
    L1ToL2MessageReaderClassic,
    L1ToL2MessageStatus,
)
from src.lib.message.message_data_parser import SubmitRetryableMessageDataParser
from src.lib.utils.helper import CaseDict
from src.lib.utils.lib import is_defined


class L1TransactionReceipt(CaseDict):
    """
    A Python equivalent of the TypeScript L1TransactionReceipt class.
    """

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

    async def is_classic(self, l2_signer_or_provider):
        provider = SignerProviderUtils.get_provider_or_throw(l2_signer_or_provider)
        network = get_l2_network(provider)
        return self.block_number < network.nitro_genesis_l1_block

    def get_message_delivered_events(self, provider):
        return parse_typed_logs(provider, "Bridge", self.logs, "MessageDelivered", is_classic=False)

    def get_inbox_message_delivered_events(self, provider):
        return parse_typed_logs(
            provider,
            "Inbox",
            self.logs,
            "InboxMessageDelivered",
            is_classic=False,
        )

    def get_message_events(self, provider):
        bridge_messages = self.get_message_delivered_events(provider)
        inbox_messages = self.get_inbox_message_delivered_events(provider)

        if len(bridge_messages) != len(inbox_messages):
            raise ArbSdkError(
                f"Unexpected missing events. Inbox message count: {len(inbox_messages)} does not equal bridge message count: {len(bridge_messages)}. {bridge_messages} {inbox_messages}"
            )

        messages = []
        for bm in bridge_messages:
            im = next(
                (i for i in inbox_messages if i["messageNum"] == bm["messageIndex"]),
                None,
            )
            if not im:
                raise ArbSdkError(f"Unexpected missing event for message index: {bm['messageIndex']}.")

            messages.append(
                {
                    "inboxMessageEvent": im,
                    "bridgeMessageEvent": bm,
                }
            )

        return messages

    async def get_eth_deposits(self, l2_provider):
        messages = self.get_message_events(l2_provider)
        eth_deposit_messages = []

        for e in messages:
            if e["bridgeMessageEvent"]["kind"] == InboxMessageKind.L1MessageType_ethDeposit.value:
                eth_deposit_message = EthDepositMessage.from_event_components(
                    l2_provider,
                    e["inboxMessageEvent"]["messageNum"],
                    e["bridgeMessageEvent"]["sender"],
                    e["inboxMessageEvent"]["data"],
                )
                eth_deposit_messages.append(eth_deposit_message)

        return eth_deposit_messages

    async def get_l1_to_l2_messages_classic(self, l2_provider):
        network = get_l2_network(l2_provider)
        chain_id = network.chain_id
        is_classic = await self.is_classic(l2_provider)

        if not is_classic:
            raise Exception(
                "This method is only for classic transactions. Use 'getL1ToL2Messages' for nitro transactions."
            )

        message_nums = [msg["messageNum"] for msg in self.get_inbox_message_delivered_events(l2_provider)]

        return [L1ToL2MessageReaderClassic(l2_provider, chain_id, message_num) for message_num in message_nums]

    async def get_l1_to_l2_messages(self, l2_signer_or_provider):
        provider = SignerProviderUtils.get_provider_or_throw(l2_signer_or_provider)
        network = get_l2_network(provider)
        chain_id = network.chain_id
        is_classic = await self.is_classic(provider)

        if is_classic:
            raise Exception(
                "This method is only for nitro transactions. Use 'getL1ToL2MessagesClassic' for classic transactions."
            )

        events = self.get_message_events(provider)
        return [
            L1ToL2Message.from_event_components(
                l2_signer_or_provider,
                chain_id,
                event["bridgeMessageEvent"]["sender"],
                event["inboxMessageEvent"]["messageNum"],
                event["bridgeMessageEvent"]["baseFeeL1"],
                SubmitRetryableMessageDataParser.parse(event["inboxMessageEvent"]["data"]),
            )
            for event in events
            if event["bridgeMessageEvent"]["kind"] == InboxMessageKind.L1MessageType_submitRetryableTx.value
            and event["bridgeMessageEvent"]["inbox"].lower() == network.eth_bridge.inbox.lower()
        ]

    def get_token_deposit_events(self, provider):
        return parse_typed_logs(provider, "L1ERC20Gateway", self.logs, "DepositInitiated", is_classic=True)

    @staticmethod
    def monkey_patch_wait(contract_transaction):
        return L1TransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_eth_deposit_wait(contract_transaction):
        return L1EthDepositTransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_contract_call_wait(tx_receipt):
        return L1ContractCallTransactionReceipt(tx_receipt)


class L1EthDepositTransactionReceipt(L1TransactionReceipt):
    async def wait_for_l2(
        self,
        l2_provider,
        confirmations=None,
        timeout=None,
    ):
        message = (await self.get_eth_deposits(l2_provider))[0]
        if not message:
            raise ArbSdkError("Unexpected missing Eth Deposit message.")

        result = await message.wait(confirmations, timeout)
        return {
            "complete": is_defined(result),
            "l2TxReceipt": result,
            "message": message,
        }


class L1ContractCallTransactionReceipt(L1TransactionReceipt):
    async def wait_for_l2(
        self,
        l2_signer_or_provider,
        confirmations=None,
        timeout=None,
    ):
        message = (await self.get_l1_to_l2_messages(l2_signer_or_provider))[0]

        if not message:
            raise ArbSdkError("Unexpected missing L1ToL2 message.")

        result = await message.wait_for_status(confirmations, timeout)

        return {
            "complete": result["status"] == L1ToL2MessageStatus.REDEEMED,
            **result,
            "message": message,
        }
