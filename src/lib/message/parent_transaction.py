from typing import Any, List, Dict

from web3.types import TxReceipt

from src.lib.data_entities.constants import ARB1_NITRO_GENESIS_L1_BLOCK
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.event import parse_typed_logs
from src.lib.data_entities.message import InboxMessageKind
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.parent_to_child_message import (
    EthDepositMessage,
    ParentToChildMessage,
    ParentToChildMessageReaderClassic,
    ParentToChildMessageStatus,
)
from src.lib.message.message_data_parser import SubmitRetryableMessageDataParser
from src.lib.utils.helper import CaseDict
from src.lib.utils.lib import is_defined


class ParentTransactionReceipt(CaseDict):
    """A Python equivalent of the TypeScript ParentTransactionReceipt class."""

    def __init__(self, tx: TxReceipt):
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

    def is_classic(self, child_signer_or_provider):
        """Check if transaction is classic"""
        provider = SignerProviderUtils.get_provider_or_throw(child_signer_or_provider)
        network = get_arbitrum_network(provider)

        # All networks except Arbitrum One started with Nitro
        if network.chain_id == 42161:
            return self.block_number < ARB1_NITRO_GENESIS_L1_BLOCK
        
        return False

    def get_message_delivered_events(self) -> List[Dict[str, Any]]:
        """Get MessageDelivered events"""
        return parse_typed_logs(
            contract_name="Bridge", 
            logs=self.logs,
            event_name="MessageDelivered",
            
        )

    def get_inbox_message_delivered_events(self) -> List[Dict[str, Any]]:
        """Get InboxMessageDelivered events"""
        return parse_typed_logs(
            contract_name="Inbox",
            logs=self.logs, 
            event_name="InboxMessageDelivered",
            
        )

    def get_message_events(self) -> List[Dict[str, Any]]:
        """Get combined message events"""
        bridge_messages = self.get_message_delivered_events()
        
        inbox_messages = self.get_inbox_message_delivered_events()

        if len(bridge_messages) != len(inbox_messages):
            raise ArbSdkError(
                f"Unexpected missing events. Inbox message count: {len(inbox_messages)} "
                f"does not equal bridge message count: {len(bridge_messages)}. "
                f"{bridge_messages} {inbox_messages}"
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

            messages.append({
                "inboxMessageEvent": im,
                "bridgeMessageEvent": bm,
            })

        return messages

    def get_eth_deposits(self, child_provider) -> List[EthDepositMessage]:
        """Get ETH deposit messages"""
        messages = self.get_message_events()
        eth_deposit_messages = []

        for e in messages:
            if e["bridgeMessageEvent"]["kind"] == InboxMessageKind.L1MessageType_ethDeposit.value:
                eth_deposit_message =  EthDepositMessage.from_event_components(
                    child_provider,
                    e["inboxMessageEvent"]["messageNum"],
                    e["bridgeMessageEvent"]["sender"],
                    e["inboxMessageEvent"]["data"],
                )
                eth_deposit_messages.append(eth_deposit_message)

        return eth_deposit_messages

    def get_parent_to_child_messages_classic(
        self, 
        child_provider
    ) -> List[ParentToChildMessageReaderClassic]:
        """Get classic parent-to-child messages"""
        network = get_arbitrum_network(child_provider)
        chain_id = network.chainId

        is_classic =  self.is_classic(child_provider)

        if not is_classic:
            raise Exception(
                "This method is only for classic transactions. "
                "Use 'getParentToChildMessages' for nitro transactions."
            )

        message_nums = [
            msg["messageNum"] 
            for msg in self.get_inbox_message_delivered_events()
        ]

        return [
            ParentToChildMessageReaderClassic(child_provider, chain_id, message_num) 
            for message_num in message_nums
        ]

    def get_parent_to_child_messages(self, child_signer_or_provider):
        """Get parent-to-child messages"""
        provider = SignerProviderUtils.get_provider_or_throw(child_signer_or_provider)
        network = get_arbitrum_network(provider)
        chain_id = network.chain_id
        is_classic =  self.is_classic(provider)

        if is_classic:
            raise Exception(
                "This method is only for nitro transactions. "
                "Use 'getParentToChildMessagesClassic' for classic transactions."
            )

        events = self.get_message_events()
        
        return [
            ParentToChildMessage.from_event_components(
                child_signer_or_provider,
                chain_id,
                event["bridgeMessageEvent"]["sender"],
                event["inboxMessageEvent"]["messageNum"],
                event["bridgeMessageEvent"]["baseFeeL1"],
                SubmitRetryableMessageDataParser.parse(event["inboxMessageEvent"]["data"]),
            )
            for event in events
            if (
                event["bridgeMessageEvent"]["kind"] == 
                    InboxMessageKind.L1MessageType_submitRetryableTx.value
                and event["bridgeMessageEvent"]["inbox"].lower() == 
                    network.ethBridge.inbox.lower()
            )
        ]

    def get_token_deposit_events(self):
        """Get token deposit events"""
        return parse_typed_logs(
            contract_name="L1ERC20Gateway",
            logs=self.logs,
            event_name="DepositInitiated",
            
        )

    @staticmethod
    def monkey_patch_wait(contract_transaction):
        """Add wait functionality to contract transaction"""
        return ParentTransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_eth_deposit_wait(contract_transaction):
        """Add ETH deposit wait functionality"""
        return ParentEthDepositTransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_contract_call_wait(tx_receipt):
        """Add contract call wait functionality"""
        return ParentContractCallTransactionReceipt(tx_receipt)
    
class ParentEthDepositTransactionReceipt(ParentTransactionReceipt):
    """
    A ParentTransactionReceipt with additional functionality that only exists
    if the transaction created a single ETH deposit.
    """
    def wait_for_child_transaction_receipt(
        self,
        child_provider,
        confirmations=None,
        timeout=None,
    ):
        
        """
        Wait for the funds to arrive on the child chain.
        
        Args:
            child_provider: Provider for child chain
            confirmations: Number of confirmations needed
            timeout: Timeout in milliseconds
            
        Returns:
            Dict containing complete status, message and child transaction receipt
        """
        message = ( self.get_eth_deposits(child_provider))[0]
        if not message:
            raise ArbSdkError("Unexpected missing Eth Deposit message.")

        result =  message.wait(confirmations, timeout)
        return {
            "complete": is_defined(result),
            "childTxReceipt": result,
            "message": message,
        }


class ParentContractCallTransactionReceipt(ParentTransactionReceipt):
    """
    A ParentTransactionReceipt with additional functionality that only exists
    if the transaction created a single call to a child chain contract - this includes
    token deposits.
    """
    def wait_for_child_transaction_receipt(
        self,
        child_signer_or_provider,
        confirmations=None,
        timeout=None,
    ):
        """
        Wait for the transaction to arrive and be executed on the child chain.
        
        Args:
            child_signer_or_provider: Signer or provider for child chain
            confirmations: Number of confirmations needed
            timeout: Timeout in milliseconds
            
        Returns:
            Dict containing complete status, message and operation result
        """
        messages =  self.get_parent_to_child_messages(child_signer_or_provider)
        if not messages or len(messages) == 0:
            raise ArbSdkError("Unexpected missing Parent-to-child message.")
            
        message = messages[0]
        result =  message.wait_for_status(confirmations, timeout)

        return {
            "complete": result["status"] == ParentToChildMessageStatus.REDEEMED,
            **result,
            "message": message,
        }


# Optional helper types for better type hints
class ParentContractTransaction:
    """Base class for parent contract transactions"""
    
    def wait(self, confirmations=None) -> ParentTransactionReceipt:
        """Wait for transaction confirmation"""
        raise NotImplementedError()


class ParentEthDepositTransaction(ParentContractTransaction):
    """Parent ETH deposit transaction"""
    
    def wait(self, confirmations=None) -> ParentEthDepositTransactionReceipt:
        """Wait for ETH deposit confirmation"""
        raise NotImplementedError()


class ParentContractCallTransaction(ParentContractTransaction):
    """Parent contract call transaction"""
    
    def wait(self, confirmations=None) -> ParentContractCallTransactionReceipt:
        """Wait for contract call confirmation"""
        raise NotImplementedError()