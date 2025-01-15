from typing import Any, Dict, List, Optional, Union

from web3 import Web3
from web3.providers import BaseProvider
from web3.types import TxReceipt

from arbitrum_py.data_entities.constants import ARB1_NITRO_GENESIS_L1_BLOCK
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.event import parse_typed_logs
from arbitrum_py.data_entities.message import InboxMessageKind
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.message.message_data_parser import SubmitRetryableMessageDataParser
from arbitrum_py.message.parent_to_child_message import (
    EthDepositMessage,
    ParentToChildMessage,
    ParentToChildMessageReaderClassic,
    ParentToChildMessageStatus,
)
from arbitrum_py.utils.helper import CaseDict
from arbitrum_py.utils.lib import is_defined


class ParentTransactionReceipt(CaseDict):
    """
    A transaction receipt for transactions sent on the parent chain.

    This class represents a transaction receipt with additional functionality specific to
    parent chain transactions in the Arbitrum ecosystem.

    Args:
        tx (TxReceipt): The transaction receipt from web3.py

    Attributes:
        to (str): The address the transaction was sent to
        from_ (str): The address that sent the transaction
        contractAddress (str): The contract address created, if the transaction was a contract creation
        transactionIndex (int): Integer of the transaction's index position in the block
        root (str): The root of the state trie after this transaction
        gasUsed (int): The amount of gas used by this specific transaction
        logsBloom (str): The bloom filter for the logs of the block
        blockHash (str): Hash of the block where this transaction was in
        transactionHash (str): Hash of the transaction
        logs (List[Dict]): Array of log objects that this transaction generated
        blockNumber (int): Block number where this transaction was in
        confirmations (int): Number of block confirmations
        cumulativeGasUsed (int): The total amount of gas used when this transaction was executed in the block
        effectiveGasPrice (int): The actual value per gas deducted from the senders account
        byzantium (bool): True if block is byzantium hard fork or later
        type (int): Transaction type
        status (int): Either 1 (success) or 0 (failure)
    """

    def __init__(self, tx: TxReceipt) -> None:
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

    def is_classic(self, child_signer_or_provider: Union[Web3, BaseProvider]) -> bool:
        """
        Check if the transaction was processed by the classic Arbitrum system.

        Args:
            child_signer_or_provider: The Web3 instance or provider for the child chain

        Returns:
            bool: True if the transaction was processed by classic Arbitrum, False otherwise
        """
        provider = SignerProviderUtils.get_provider_or_throw(child_signer_or_provider)
        network = get_arbitrum_network(provider)

        # All networks except Arbitrum One started with Nitro
        if network.chain_id == 42161:
            return self.block_number < ARB1_NITRO_GENESIS_L1_BLOCK

        return False

    def get_message_delivered_events(self) -> List[Dict[str, Any]]:
        """
        Get MessageDelivered events from the transaction logs.

        Returns:
            List[Dict[str, Any]]: List of parsed MessageDelivered events
        """
        return parse_typed_logs(
            contract_name="Bridge",
            logs=self.logs,
            event_name="MessageDelivered",
        )

    def get_inbox_message_delivered_events(self) -> List[Dict[str, Any]]:
        """
        Get InboxMessageDelivered events from the transaction logs.

        Returns:
            List[Dict[str, Any]]: List of parsed InboxMessageDelivered events
        """
        return parse_typed_logs(
            contract_name="Inbox",
            logs=self.logs,
            event_name="InboxMessageDelivered",
        )

    def get_message_events(self) -> List[Dict[str, Any]]:
        """
        Get combined message events from both Bridge and Inbox contracts.

        This method combines MessageDelivered events from the Bridge contract with
        InboxMessageDelivered events from the Inbox contract, matching them by message index.

        Returns:
            List[Dict[str, Any]]: List of combined message events

        Raises:
            ArbSdkError: If there is a mismatch in the number of events or if a matching
                        event is not found
        """
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
                raise ArbSdkError(f"Unexpected missing event for message index: {bm['messageIndex']}.")

            messages.append(
                {
                    "inboxMessageEvent": im,
                    "bridgeMessageEvent": bm,
                }
            )
        return messages

    def get_eth_deposits(self, child_provider: Union[Web3, BaseProvider]) -> List[EthDepositMessage]:
        """
        Get ETH deposit messages from the transaction logs.

        Args:
            child_provider: The Web3 instance or provider for the child chain

        Returns:
            List[EthDepositMessage]: List of ETH deposit messages
        """
        messages = self.get_message_events()
        eth_deposit_messages = []

        for e in messages:
            if e["bridgeMessageEvent"]["kind"] == InboxMessageKind.L1MessageType_ethDeposit.value:
                eth_deposit_message = EthDepositMessage.from_event_components(
                    child_provider,
                    e["inboxMessageEvent"]["messageNum"],
                    e["bridgeMessageEvent"]["sender"],
                    e["inboxMessageEvent"]["data"],
                )
                eth_deposit_messages.append(eth_deposit_message)

        return eth_deposit_messages

    def get_parent_to_child_messages_classic(
        self, child_provider: Union[Web3, BaseProvider]
    ) -> List[ParentToChildMessageReaderClassic]:
        """
        Get classic parent-to-child messages from the transaction logs.

        Args:
            child_provider: The Web3 instance or provider for the child chain

        Returns:
            List[ParentToChildMessageReaderClassic]: List of classic parent-to-child messages

        Raises:
            Exception: If the transaction is not a classic transaction
        """
        network = get_arbitrum_network(child_provider)
        chain_id = network.chainId

        is_classic = self.is_classic(child_provider)

        if not is_classic:
            raise Exception(
                "This method is only for classic transactions. Use 'get_parent_to_child_messages' for nitro transactions."
            )

        message_nums = [msg["messageNum"] for msg in self.get_inbox_message_delivered_events()]

        return [
            ParentToChildMessageReaderClassic(child_provider, chain_id, message_num) for message_num in message_nums
        ]

    def get_parent_to_child_messages(
        self, child_signer_or_provider: Union[Web3, BaseProvider]
    ) -> List[ParentToChildMessage]:
        """
        Get parent-to-child messages from the transaction logs.

        Args:
            child_signer_or_provider: The Web3 instance or provider for the child chain

        Returns:
            List[ParentToChildMessage]: List of parent-to-child messages

        Raises:
            Exception: If the transaction is not a nitro transaction
        """
        provider = SignerProviderUtils.get_provider_or_throw(child_signer_or_provider)
        network = get_arbitrum_network(provider)
        chain_id = network.chain_id
        is_classic = self.is_classic(provider)

        if is_classic:
            raise Exception(
                "This method is only for nitro transactions. Use 'get_parent_to_child_messages_classic' for classic transactions."
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
                event["bridgeMessageEvent"]["kind"] == InboxMessageKind.L1MessageType_submitRetryableTx.value
                and event["bridgeMessageEvent"]["inbox"].lower() == network.ethBridge.inbox.lower()
            )
        ]

    def get_token_deposit_events(self) -> List[Dict[str, Any]]:
        """
        Get token deposit events from the transaction logs.

        Returns:
            List[Dict[str, Any]]: List of parsed token deposit events
        """
        return parse_typed_logs(
            contract_name="L1ERC20Gateway",
            logs=self.logs,
            event_name="DepositInitiated",
        )

    @staticmethod
    def monkey_patch_wait(contract_transaction: TxReceipt) -> "ParentTransactionReceipt":
        """
        Add wait functionality to contract transaction.

        Args:
            contract_transaction: The contract transaction

        Returns:
            ParentTransactionReceipt: The transaction receipt
        """
        return ParentTransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_eth_deposit_wait(
        contract_transaction: TxReceipt,
    ) -> "ParentEthDepositTransactionReceipt":
        """
        Add ETH deposit wait functionality.

        Args:
            contract_transaction: The contract transaction

        Returns:
            ParentEthDepositTransactionReceipt: The transaction receipt
        """
        return ParentEthDepositTransactionReceipt(contract_transaction)

    @staticmethod
    def monkey_patch_contract_call_wait(
        tx_receipt: TxReceipt,
    ) -> "ParentContractCallTransactionReceipt":
        """
        Add contract call wait functionality.

        Args:
            tx_receipt: The transaction receipt

        Returns:
            ParentContractCallTransactionReceipt: The transaction receipt
        """
        return ParentContractCallTransactionReceipt(tx_receipt)


class ParentEthDepositTransactionReceipt(ParentTransactionReceipt):
    """
    A transaction receipt for ETH deposits from parent to child chain.

    This class extends ParentTransactionReceipt with additional functionality specific to
    ETH deposit transactions.

    Attributes:
        complete (bool): Whether the transaction is complete
        message (EthDepositMessage): The ETH deposit message
    """

    def wait_for_child_transaction_receipt(
        self,
        child_provider: Union[Web3, BaseProvider],
        confirmations: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Wait for the ETH deposit to arrive on the child chain.

        Args:
            child_provider: The Web3 instance or provider for the child chain
            confirmations: Number of confirmations to wait for (optional)
            timeout: Maximum time to wait in milliseconds (optional)

        Returns:
            Dict[str, Any]: A dictionary containing:
                - complete (bool): Whether the transaction is complete
                - message (EthDepositMessage): The ETH deposit message
                - status (ParentToChildMessageStatus): Current status of the message
                - childTxReceipt (Optional[TxReceipt]): Receipt of the child transaction if available
        """
        message = (self.get_eth_deposits(child_provider))[0]
        if not message:
            raise ArbSdkError("Unexpected missing Eth Deposit message.")

        result = message.wait(confirmations, timeout)
        return {
            "complete": is_defined(result),
            "childTxReceipt": result,
            "message": message,
        }


class ParentContractCallTransactionReceipt(ParentTransactionReceipt):
    """
    A transaction receipt for contract calls from parent to child chain.

    This class extends ParentTransactionReceipt with additional functionality specific to
    contract call transactions, including token deposits.

    Attributes:
        complete (bool): Whether the transaction is complete
        message (ParentToChildMessageReaderOrWriter): The parent-to-child message
    """

    def wait_for_child_transaction_receipt(
        self,
        child_signer_or_provider: Union[Web3, BaseProvider],
        confirmations: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Wait for the transaction to arrive and be executed on the child chain.

        Args:
            child_signer_or_provider: The Web3 instance or provider for the child chain
            confirmations: Number of confirmations to wait for (optional)
            timeout: Maximum time to wait in milliseconds (optional)

        Returns:
            Dict[str, Any]: A dictionary containing:
                - complete (bool): Whether the transaction is complete
                - message (ParentToChildMessageReaderOrWriter): The parent-to-child message
                - status (ParentToChildMessageStatus): Current status of the message
                - childTxReceipt (Optional[TxReceipt]): Receipt of the child transaction if available
        """
        messages = self.get_parent_to_child_messages(child_signer_or_provider)
        if not messages or len(messages) == 0:
            raise ArbSdkError("Unexpected missing Parent-to-child message.")

        message = messages[0]
        result = message.wait_for_status(confirmations, timeout)

        return {
            "complete": result["status"] == ParentToChildMessageStatus.REDEEMED,
            **result,
            "message": message,
        }


class ParentContractTransaction:
    """
    Base class for parent chain contract transactions.

    This class provides a common interface for all parent chain transactions.
    """

    def wait(self, confirmations: Optional[int] = None) -> ParentTransactionReceipt:
        """
        Wait for transaction confirmation.

        Args:
            confirmations: Number of confirmations to wait for (optional)

        Returns:
            ParentTransactionReceipt: The transaction receipt
        """
        raise NotImplementedError()


class ParentEthDepositTransaction(ParentContractTransaction):
    """
    Parent chain ETH deposit transaction.

    This class represents a transaction that deposits ETH from the parent chain to the child chain.
    """

    def wait(self, confirmations: Optional[int] = None) -> ParentEthDepositTransactionReceipt:
        """
        Wait for ETH deposit confirmation.

        Args:
            confirmations: Number of confirmations to wait for (optional)

        Returns:
            ParentEthDepositTransactionReceipt: The transaction receipt
        """
        raise NotImplementedError()


class ParentContractCallTransaction(ParentContractTransaction):
    """
    Parent chain contract call transaction.

    This class represents a transaction that calls a contract on the child chain from the parent chain.
    """

    def wait(self, confirmations: Optional[int] = None) -> ParentContractCallTransactionReceipt:
        """
        Wait for contract call confirmation.

        Args:
            confirmations: Number of confirmations to wait for (optional)

        Returns:
            ParentContractCallTransactionReceipt: The transaction receipt
        """
        raise NotImplementedError()
