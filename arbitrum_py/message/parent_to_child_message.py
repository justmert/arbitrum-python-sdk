import math
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import rlp
from web3 import Web3
from web3.exceptions import ContractCustomError
from web3.types import HexStr, TxReceipt, Wei

from arbitrum_py.data_entities.constants import (
    ADDRESS_ZERO,
    ARB_RETRYABLE_TX_ADDRESS,
    DEFAULT_DEPOSIT_TIMEOUT,
    SEVEN_DAYS_IN_SECONDS,
)
from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.data_entities.signer_or_provider import SignerProviderUtils
from arbitrum_py.message.child_transaction import ChildTransactionReceipt
from arbitrum_py.utils.event_fetcher import EventFetcher
from arbitrum_py.utils.helper import load_contract, to_checksum_address
from arbitrum_py.utils.lib import get_transaction_receipt, is_defined


def int_to_bytes(value: int) -> bytes:
    """
    Convert an integer to its bytes representation.

    Args:
        value: Integer value to convert

    Returns:
        Bytes representation of the integer
    """
    return Web3.to_bytes(value)


def hex_to_bytes(value: str) -> bytes:
    """
    Convert a hex string to bytes.

    Args:
        value: Hex string (with or without '0x' prefix)

    Returns:
        Bytes representation of the hex string
    """
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def zero_pad(value: bytes, length: int) -> bytes:
    """
    Pad a byte string with leading zeros to reach specified length.

    Args:
        value: Bytes to pad
        length: Desired length after padding

    Returns:
        Zero-padded bytes
    """
    return value.rjust(length, b"\x00")


def format_number(value: int) -> bytes:
    """
    Format a number as a minimal-length byte string.

    Args:
        value: Number to format

    Returns:
        Minimal length bytes representation of the number
    """
    hex_str = Web3.to_hex(value)[2:].lstrip("0")
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str
    return bytes.fromhex(hex_str)


def concat(*args: Union[bytes, List[bytes], Tuple[bytes, ...]]) -> bytes:
    """
    Concatenate byte strings.

    Args:
        *args: Either multiple byte strings or a single iterable of byte strings

    Returns:
        Concatenated bytes
    """
    if len(args) == 1 and isinstance(args[0], (list, tuple)) and not isinstance(args[0], (bytes, bytearray)):
        iterable = args[0]
    else:
        iterable = args
    return b"".join(iterable)


class ParentToChildMessageStatus(Enum):
    """
    Status enum for parent-to-child messages.

    Attributes:
        NOT_YET_CREATED (int): The retryable ticket has yet to be created
        CREATION_FAILED (int): An attempt was made to create the retryable ticket, but it failed
        FUNDS_DEPOSITED_ON_CHILD (int): The retryable ticket has been created but has not been redeemed
        REDEEMED (int): The retryable ticket has been redeemed and the chain transaction has been executed
        EXPIRED (int): The message has either expired or has been canceled
    """

    NOT_YET_CREATED = 1
    CREATION_FAILED = 2
    FUNDS_DEPOSITED_ON_CHILD = 3
    REDEEMED = 4
    EXPIRED = 5


class EthDepositMessageStatus(Enum):
    """
    Status enum for ETH deposit messages.

    Attributes:
        PENDING (int): ETH is not deposited on Chain yet
        DEPOSITED (int): ETH is deposited successfully on Chain
    """

    PENDING = 1
    DEPOSITED = 2


class ParentToChildMessage:
    """
    Base class for messages sent from parent chain to child chain.

    This class handles the core functionality for parent-to-child messages,
    including retryable ticket creation and management.

    Args:
        chain_id: The ID of the child chain
        sender: The address of the message sender
        message_number: The sequential number of the message
        parent_base_fee: The base fee on the parent chain
        message_data: Dictionary containing message parameters:
            - destAddress: Destination address
            - l2CallValue: Call value on L2
            - l1Value: Value on L1
            - maxSubmissionFee: Maximum submission fee
            - excessFeeRefundAddress: Address for excess fee refund
            - callValueRefundAddress: Address for call value refund
            - gasLimit: Gas limit
            - maxFeePerGas: Maximum fee per gas
            - data: Call data
    """

    def __init__(
        self,
        chain_id: int,
        sender: str,
        message_number: int,
        parent_base_fee: int,
        message_data: Dict[str, Any],
    ) -> None:
        self.chain_id = chain_id
        self.sender = sender
        self.message_number = message_number
        self.parent_base_fee = parent_base_fee
        self.message_data = message_data
        self.retryable_creation_id = self.calculate_submit_retryable_id(
            chain_id,
            sender,
            message_number,
            parent_base_fee,
            message_data["destAddress"],
            message_data["l2CallValue"],
            message_data["l1Value"],
            message_data["maxSubmissionFee"],
            message_data["excessFeeRefundAddress"],
            message_data["callValueRefundAddress"],
            message_data["gasLimit"],
            message_data["maxFeePerGas"],
            message_data["data"],
        )

    @staticmethod
    def calculate_submit_retryable_id(
        child_chain_id: int,
        from_address: str,
        message_number: int,
        parent_base_fee: int,
        dest_address: str,
        child_call_value: int,
        parent_call_value: int,
        max_submission_fee: int,
        excess_fee_refund_address: str,
        call_value_refund_address: str,
        gas_limit: int,
        max_fee_per_gas: int,
        data: str,
    ) -> HexStr:
        """
        Calculate the unique identifier for a retryable submission.

        Args:
            child_chain_id: ID of the child chain
            from_address: Address sending the message
            message_number: Sequential message number
            parent_base_fee: Base fee on parent chain
            dest_address: Destination address
            child_call_value: Call value on child chain
            parent_call_value: Call value on parent chain
            max_submission_fee: Maximum submission fee
            excess_fee_refund_address: Address for excess fee refund
            call_value_refund_address: Address for call value refund
            gas_limit: Gas limit
            max_fee_per_gas: Maximum fee per gas
            data: Call data

        Returns:
            Unique identifier for the retryable submission
        """
        chain_id = child_chain_id
        msg_num = message_number
        from_addr = Web3.to_checksum_address(from_address)
        dest_addr = "0x" if dest_address == ADDRESS_ZERO else Web3.to_checksum_address(dest_address)
        call_value_refund_addr = Web3.to_checksum_address(call_value_refund_address)
        excess_fee_refund_addr = Web3.to_checksum_address(excess_fee_refund_address)

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(from_addr[2:]),
            format_number(parent_base_fee),
            format_number(parent_call_value),
            format_number(max_fee_per_gas),
            format_number(gas_limit),
            bytes.fromhex(dest_addr[2:]) if dest_addr != "0x" else b"",
            format_number(child_call_value),
            bytes.fromhex(call_value_refund_addr[2:]),
            format_number(max_submission_fee),
            bytes.fromhex(excess_fee_refund_addr[2:]),
            bytes.fromhex(data[2:]),
        ]

        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b"\x69" + rlp_encoded

        retryable_tx_id = Web3.keccak(rlp_enc_with_type)
        return retryable_tx_id.hex()

    @staticmethod
    def from_event_components(
        chain_signer_or_provider: Union[SignerProviderUtils, Any],
        chain_id: int,
        sender: str,
        message_number: int,
        parent_base_fee: int,
        message_data: Dict[str, Any],
    ) -> Union["ParentToChildMessageReader", "ParentToChildMessageWriter"]:
        """
        Create a ParentToChildMessage instance from event components.

        Args:
            chain_signer_or_provider: Signer or provider for the chain
            chain_id: ID of the child chain
            sender: Address of the message sender
            message_number: Sequential message number
            parent_base_fee: Base fee on parent chain
            message_data: Dictionary containing message parameters

        Returns:
            ParentToChildMessage instance
        """
        if SignerProviderUtils.is_signer(chain_signer_or_provider):
            return ParentToChildMessageWriter(
                chain_signer_or_provider,
                chain_id,
                sender,
                message_number,
                parent_base_fee,
                message_data,
            )
        else:
            return ParentToChildMessageReader(
                chain_signer_or_provider,
                chain_id,
                sender,
                message_number,
                parent_base_fee,
                message_data,
            )


class ParentToChildMessageReader(ParentToChildMessage):
    """
    Reader class for parent-to-child messages.

    This class extends the base ParentToChildMessage class and provides
    additional functionality for reading and managing parent-to-child messages.

    Args:
        child_provider: Provider for the child chain
        chain_id: ID of the child chain
        sender: Address of the message sender
        message_number: Sequential message number
        parent_base_fee: Base fee on parent chain
        message_data: Dictionary containing message parameters
    """

    def __init__(
        self,
        child_provider: Any,
        chain_id: int,
        sender: str,
        message_number: int,
        parent_base_fee: int,
        message_data: Dict[str, Any],
    ) -> None:
        super().__init__(chain_id, sender, message_number, parent_base_fee, message_data)
        self.child_provider = child_provider

        self.retryable_creation_receipt = None

    def get_retryable_creation_receipt(
        self, confirmations: Optional[int] = None, timeout: Optional[int] = None
    ) -> Optional[TxReceipt]:
        """
        Get the receipt for the retryable creation transaction.

        Args:
            confirmations: Number of confirmations to wait for
            timeout: Timeout in seconds

        Returns:
            Receipt for the retryable creation transaction, or None if not found
        """
        if not self.retryable_creation_receipt:

            self.retryable_creation_receipt = get_transaction_receipt(
                self.child_provider, self.retryable_creation_id, confirmations, timeout
            )

        return self.retryable_creation_receipt or None

    def get_auto_redeem_attempt(self) -> Optional[TxReceipt]:
        """
        Get the auto-redeem attempt for the retryable creation transaction.

        Returns:
            Receipt for the auto-redeem attempt, or None if not found
        """
        creation_receipt = self.get_retryable_creation_receipt()
        if creation_receipt:

            chain_receipt = ChildTransactionReceipt(creation_receipt)

            redeem_events = chain_receipt.get_redeem_scheduled_events()

            if len(redeem_events) == 1:
                try:
                    return self.child_provider.eth.get_transaction_receipt(redeem_events[0]["retryTxHash"])
                except Exception as e:

                    pass
            elif len(redeem_events) > 1:
                raise ArbSdkError(
                    f"Unexpected number of redeem events for retryable creation tx. {creation_receipt} {redeem_events}"
                )

        return None

    def get_successful_redeem(self) -> Dict[str, Any]:
        """
        Get the successful redeem for the retryable creation transaction.

        Returns:
            Dictionary containing the successful redeem data
        """

        chainNetwork = get_arbitrum_network(self.child_provider)
        event_fetcher = EventFetcher(self.child_provider)
        creation_receipt = self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return {"status": ParentToChildMessageStatus.NOT_YET_CREATED}

        if creation_receipt.status == 0:
            return {"status": ParentToChildMessageStatus.CREATION_FAILED}

        auto_redeem = self.get_auto_redeem_attempt()

        if auto_redeem and auto_redeem.status == 1:

            return {"childTxReceipt": auto_redeem, "status": ParentToChildMessageStatus.REDEEMED}

        if self.retryable_exists():

            return {"status": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD}

        increment = 1000
        from_block = self.child_provider.eth.get_block(creation_receipt.blockNumber)
        timeout = from_block.timestamp + (chainNetwork.retryableLifetimeSeconds or SEVEN_DAYS_IN_SECONDS)

        queried_range = []
        max_block = self.child_provider.eth.block_number

        while from_block.number < max_block:
            to_block_number = min(from_block.number + increment, max_block)
            outer_block_range = {"from": from_block.number, "to": to_block_number}
            queried_range.append(outer_block_range)

            redeem_events = event_fetcher.get_events(
                contract_factory="ArbRetryableTx",
                event_name="RedeemScheduled",
                argument_filters={"ticketId": self.retryable_creation_id},
                filter={
                    "fromBlock": outer_block_range["from"],
                    "toBlock": outer_block_range["to"],
                    "address": ARB_RETRYABLE_TX_ADDRESS,
                },
            )

            successful_redeems = []
            for e in redeem_events:
                receipt = get_transaction_receipt(self.child_provider, e.event["retryTxHash"])
                if receipt and receipt.status == 1:
                    successful_redeems.append(receipt)

            if len(successful_redeems) > 1:
                raise ArbSdkError(f"Unexpected number of successful redeems for ticket {self.retryable_creation_id}.")
            if len(successful_redeems) == 1:
                return {
                    "childTxReceipt": successful_redeems[0],
                    "status": ParentToChildMessageStatus.REDEEMED,
                }

            to_block = self.child_provider.eth.get_block(to_block_number)
            if to_block.timestamp > timeout:
                while queried_range:
                    block_range = queried_range.pop(0)
                    keepalive_events = event_fetcher.get_events(
                        contract_factory="ArbRetryableTx",
                        event_name="LifetimeExtended",
                        argument_filters={"ticketId": self.retryable_creation_id},
                        filter={
                            "fromBlock": block_range["from"],
                            "toBlock": block_range["to"],
                            "address": ARB_RETRYABLE_TX_ADDRESS,
                        },
                    )
                    if keepalive_events:
                        timeout = sorted([e.event["newTimeout"] for e in keepalive_events], reverse=True)[0]
                        break

                if to_block.timestamp > timeout:
                    break

                while len(queried_range) > 1:
                    queried_range.pop(0)

            processed_seconds = to_block.timestamp - from_block.timestamp
            if processed_seconds != 0:
                increment = math.ceil((increment * 86400) / processed_seconds)

            from_block = to_block

        return {"status": ParentToChildMessageStatus.EXPIRED}

    def is_expired(self) -> bool:
        """
        Check if the message is expired.

        @deprecated Will be removed in v3.0.0

        Returns:
            True if the message is expired, False otherwise
        """
        return self.retryable_exists()

    def retryable_exists(self) -> bool:
        """
        Check if the retryable ticket exists.

        Returns:
            True if the retryable ticket exists, False otherwise
        """
        current_timestamp = (self.child_provider.eth.get_block("latest")).timestamp
        try:
            timeout_timestamp = self.get_timeout()
            return current_timestamp <= timeout_timestamp
        except ContractCustomError as err:
            if err.data == "0x80698456":  # NoTicketWithID error
                return False
            raise err

    def status(self) -> int:
        """
        Get the status of the message.

        Returns:
            Status of the message
        """
        return (self.get_successful_redeem())["status"]

    def wait_for_status(self, confirmations: Optional[int] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Wait for the status of the message.

        Args:
            confirmations: Number of confirmations to wait for
            timeout: Timeout in seconds

        Returns:
            Dictionary containing the status data
        """
        chosen_timeout = timeout if is_defined(timeout) else DEFAULT_DEPOSIT_TIMEOUT

        _retryable_creation_receipt = self.get_retryable_creation_receipt(confirmations, chosen_timeout)
        if not _retryable_creation_receipt:
            if confirmations or chosen_timeout:
                raise ArbSdkError(f"Timed out waiting for retryable creation receipt: {self.retryable_creation_id}.")
            raise ArbSdkError(f"Retryable creation receipt not found {self.retryable_creation_id}.")

        return self.get_successful_redeem()

    @staticmethod
    def get_lifetime(child_provider: Any) -> int:
        """
        Get the lifetime of the retryable ticket.

        Args:
            child_provider: Provider for the child chain

        Returns:
            Lifetime of the retryable ticket
        """
        arb_retryable = load_contract(
            provider=child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
        )
        return arb_retryable.functions.getLifetime().call()

    def get_timeout(self) -> int:
        """
        Get the timeout of the retryable ticket.

        Returns:
            Timeout of the retryable ticket
        """
        arb_retryable = load_contract(
            provider=self.child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
        )
        return arb_retryable.functions.getTimeout(self.retryable_creation_id).call()

    def get_beneficiary(self) -> str:
        """
        Get the beneficiary of the retryable ticket.

        Returns:
            Beneficiary of the retryable ticket
        """
        arb_retryable = load_contract(
            provider=self.child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
        )
        return arb_retryable.functions.getBeneficiary(self.retryable_creation_id).call()


class ParentToChildMessageReaderClassic:
    """
    Classic reader class for parent-to-child messages.

    This class provides functionality for reading and managing parent-to-child messages
    in a classic manner.

    Args:
        child_provider: Provider for the child chain
        chain_id: ID of the child chain
        message_number: Sequential message number
    """

    def __init__(
        self,
        child_provider: Any,
        chain_id: int,
        message_number: int,
    ) -> None:
        self.message_number = message_number
        self.child_provider = child_provider
        self.retryable_creation_id = ParentToChildMessageReaderClassic.calculate_retryable_creation_id(
            chain_id, message_number
        )
        self.auto_redeem_id = ParentToChildMessageReaderClassic.calculate_auto_redeem_id(self.retryable_creation_id)
        self.child_tx_hash = ParentToChildMessageReaderClassic.calculate_chain_tx_hash(self.retryable_creation_id)
        self.retryable_creation_receipt = None

    @staticmethod
    def calculate_retryable_creation_id(chain_id: int, message_number: int) -> HexStr:
        """
        Calculate the unique identifier for a retryable creation.

        Args:
            chain_id: ID of the child chain
            message_number: Sequential message number

        Returns:
            Unique identifier for the retryable creation
        """

        def bit_flip(num: int) -> int:
            return num | 1 << 255

        data = concat(
            zero_pad(int_to_bytes(chain_id), 32),
            zero_pad(int_to_bytes(bit_flip(message_number)), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_auto_redeem_id(retryable_creation_id: HexStr) -> HexStr:
        """
        Calculate the unique identifier for an auto-redeem.

        Args:
            retryable_creation_id: Unique identifier for the retryable creation

        Returns:
            Unique identifier for the auto-redeem
        """
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(1), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_chain_tx_hash(retryable_creation_id: HexStr) -> HexStr:
        """
        Calculate the unique identifier for a chain transaction.

        Args:
            retryable_creation_id: Unique identifier for the retryable creation

        Returns:
            Unique identifier for the chain transaction
        """
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(0), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_chain_derived_hash(retryable_creation_id: HexStr) -> HexStr:
        """
        Calculate the unique identifier for a chain-derived hash.

        Args:
            retryable_creation_id: Unique identifier for the retryable creation

        Returns:
            Unique identifier for the chain-derived hash
        """
        data = concat(
            [
                zero_pad(hex_to_bytes(retryable_creation_id), 32),
                # BN 0 meaning Chain TX
                zero_pad(int_to_bytes(0), 32),
            ]
        )
        return Web3.keccak(data).hex()

    def get_retryable_creation_receipt(
        self, confirmations: Optional[int] = None, timeout: Optional[int] = None
    ) -> Optional[TxReceipt]:
        """
        Get the receipt for the retryable creation transaction.

        Args:
            confirmations: Number of confirmations to wait for
            timeout: Timeout in seconds

        Returns:
            Receipt for the retryable creation transaction, or None if not found
        """
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = get_transaction_receipt(
                self.child_provider, self.retryable_creation_id, confirmations, timeout
            )
        return self.retryable_creation_receipt

    def status(self) -> int:
        """
        Get the status of the message.

        Returns:
            Status of the message
        """
        creation_receipt = self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return ParentToChildMessageStatus.NOT_YET_CREATED

        if creation_receipt.status == 0:
            return ParentToChildMessageStatus.CREATION_FAILED

        chain_derived_hash = ParentToChildMessageReaderClassic.calculate_chain_derived_hash(self.retryable_creation_id)

        chain_tx_receipt = get_transaction_receipt(self.child_provider, chain_derived_hash)

        if chain_tx_receipt and chain_tx_receipt.status == 1:
            return ParentToChildMessageStatus.REDEEMED

        return ParentToChildMessageStatus.EXPIRED


class ParentToChildMessageWriter(ParentToChildMessageReader):
    """
    Writer class for parent-to-child messages.

    This class extends the ParentToChildMessageReader class and provides
    additional functionality for writing and managing parent-to-child messages.

    Args:
        chain_signer: Signer for the chain
        chain_id: ID of the child chain
        sender: Address of the message sender
        message_number: Sequential message number
        parent_base_fee: Base fee on parent chain
        message_data: Dictionary containing message parameters
    """

    def __init__(
        self,
        chain_signer: Any,
        chain_id: int,
        sender: str,
        message_number: int,
        parent_base_fee: int,
        message_data: Dict[str, Any],
    ) -> None:
        if not chain_signer.provider:
            raise ArbSdkError("Signer not connected to provider.")

        super().__init__(
            chain_signer.provider,
            chain_id,
            sender,
            message_number,
            parent_base_fee,
            message_data,
        )
        self.chain_signer = chain_signer

    def redeem(self, overrides: Optional[Dict[str, Any]] = None) -> ChildTransactionReceipt:
        """
        Redeem the retryable ticket.

        Args:
            overrides: Overrides for the redeem transaction

        Returns:
            Receipt for the redeem transaction
        """
        status = self.status()
        if status == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD:
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.chain_signer.provider,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.chain_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]

            if "nonce" not in overrides:
                overrides["nonce"] = self.chain_signer.provider.eth.get_transaction_count(
                    self.chain_signer.account.address
                )

            # ---
            # if 'gas' not in overrides:
            #     gas_estimate = self.chain_signer.provider.eth.estimate_gas(overrides)
            #     overrides['gas'] = gas_estimate

            # if 'gasPrice' not in overrides:
            #     if 'maxPriorityFeePerGas' in overrides or 'maxFeePerGas' in overrides:
            #         pass
            #     else:
            #         overrides['gasPrice'] = self.chain_signer.provider.eth.gas_price

            # if 'chainId' not in overrides:
            #     overrides['chainId'] = self.chain_signer.provider.eth.chain_id

            # ---
            redeem_tx = arb_retryable_tx.functions.redeem(self.retryable_creation_id).build_transaction(overrides)
            signed_tx = self.chain_signer.account.sign_transaction(redeem_tx)
            tx_hash = self.chain_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

            tx_receipt = self.chain_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

            return ChildTransactionReceipt.to_redeem_transaction(
                ChildTransactionReceipt.monkey_patch_wait(tx_receipt), self.child_provider
            )
        else:
            raise ArbSdkError(
                f"Cannot redeem as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )

    def cancel(self, overrides: Optional[Dict[str, Any]] = None) -> TxReceipt:
        """
        Cancel the retryable ticket.

        Args:
            overrides: Overrides for the cancel transaction

        Returns:
            Receipt for the cancel transaction
        """
        status = self.status()
        if status == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD:
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.chain_signer.provider,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.chain_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]

            if "nonce" not in overrides:
                overrides["nonce"] = self.chain_signer.provider.eth.get_transaction_count(
                    self.chain_signer.account.address
                )

            redeem_tx = arb_retryable_tx.functions.cancel(self.retryable_creation_id).build_transaction(overrides)
            signed_tx = self.chain_signer.account.sign_transaction(redeem_tx)
            tx_hash = self.chain_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

            return self.chain_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        else:
            raise ArbSdkError(
                f"Cannot cancel as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )

    def keep_alive(self, overrides: Optional[Dict[str, Any]] = None) -> TxReceipt:
        """
        Keep the retryable ticket alive.

        Args:
            overrides: Overrides for the keep alive transaction

        Returns:
            Receipt for the keep alive transaction
        """
        status = self.status()
        if status == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD:
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.chain_signer.provider,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.chain_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]

            if "nonce" not in overrides:
                overrides["nonce"] = self.chain_signer.provider.eth.get_transaction_count(
                    self.chain_signer.account.address
                )

            redeem_tx = arb_retryable_tx.functions.keepalive(self.retryable_creation_id).build_transaction(overrides)
            signed_tx = self.chain_signer.account.sign_transaction(redeem_tx)
            tx_hash = self.chain_signer.provider.eth.send_raw_transaction(signed_tx.rawTransaction)

            return self.chain_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        else:
            raise ArbSdkError(
                f"Cannot keep alive as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )


class EthDepositMessage:
    """
    Class for ETH deposit messages.

    This class provides functionality for managing ETH deposit messages.

    Args:
        child_provider: Provider for the child chain
        child_chain_id: ID of the child chain
        message_number: Sequential message number
        from_address: Address sending the message
        to_address: Destination address
        value: Value of the message
    """

    def __init__(
        self,
        child_provider: Any,
        child_chain_id: int,
        message_number: int,
        from_address: str,
        to_address: str,
        value: Wei,
    ) -> None:
        self.child_provider = child_provider
        self.child_chain_id = child_chain_id
        self.message_number = message_number
        self.from_address = from_address
        self.to = to_address
        self.value = value
        self.child_tx_hash = self.calculate_deposit_tx_id(
            child_chain_id, message_number, from_address, to_address, value
        )
        self.child_tx_receipt = None

    @staticmethod
    def calculate_deposit_tx_id(
        child_chain_id: int,
        message_number: int,
        from_address: str,
        to_address: str,
        value: Wei,
    ) -> HexStr:
        """
        Calculate the unique identifier for a deposit transaction.

        Args:
            child_chain_id: ID of the child chain
            message_number: Sequential message number
            from_address: Address sending the message
            to_address: Destination address
            value: Value of the message

        Returns:
            Unique identifier for the deposit transaction
        """
        chain_id = child_chain_id
        msg_num = message_number

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(to_checksum_address(from_address)[2:]),
            bytes.fromhex(to_checksum_address(to_address)[2:]),
            format_number(value),
        ]

        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b"\x64" + rlp_encoded

        tx_id = Web3.keccak(rlp_enc_with_type)
        return tx_id.hex()

    @staticmethod
    def from_event_components(
        child_provider: Any,
        message_number: int,
        sender_addr: str,
        inbox_message_event_data: str,
    ) -> "EthDepositMessage":
        """
        Create an EthDepositMessage instance from event components.

        Args:
            child_provider: Provider for the child chain
            message_number: Sequential message number
            sender_addr: Address sending the message
            inbox_message_event_data: Event data for the inbox message

        Returns:
            EthDepositMessage instance
        """
        chain_id = child_provider.eth.chain_id
        parsed_data = EthDepositMessage.parse_eth_deposit_data(inbox_message_event_data)
        return EthDepositMessage(
            child_provider,
            chain_id,
            message_number,
            sender_addr,
            parsed_data["to"],
            parsed_data["value"],
        )

    @staticmethod
    def parse_eth_deposit_data(event_data: str) -> Dict[str, Any]:
        """
        Parse the event data for an ETH deposit message.

        Args:
            event_data: Event data for the ETH deposit message

        Returns:
            Dictionary containing the parsed data
        """
        if isinstance(event_data, bytes):
            event_data = Web3.to_hex(event_data)

        address_end = 2 + 20 * 2
        to_address = to_checksum_address("0x" + event_data[2:address_end])
        value_hex = event_data[address_end:]
        if value_hex.startswith("0"):
            value_hex = value_hex.lstrip("0")
        if not value_hex:
            value_hex = "0"

        value = int(value_hex, 16) if value_hex != "0" else 0
        return {"to": to_address, "value": value}

    def status(self) -> int:
        """
        Get the status of the message.

        Returns:
            Status of the message
        """
        receipt = get_transaction_receipt(self.child_provider, self.child_tx_hash)
        return EthDepositMessageStatus.DEPOSITED if receipt is not None else EthDepositMessageStatus.PENDING

    def wait(self, confirmations: Optional[int] = None, timeout: Optional[int] = None) -> Optional[TxReceipt]:
        """
        Wait for the message to be deposited.

        Args:
            confirmations: Number of confirmations to wait for
            timeout: Timeout in seconds

        Returns:
            Receipt for the deposit transaction, or None if not found
        """
        chosen_timeout = timeout if is_defined(timeout) else DEFAULT_DEPOSIT_TIMEOUT

        if not self.child_tx_receipt:
            self.child_tx_receipt = get_transaction_receipt(
                self.child_provider, self.child_tx_hash, confirmations, chosen_timeout
            )

        return self.child_tx_receipt or None
