import math
import rlp
from web3 import Web3
from web3.exceptions import ContractCustomError

from src.lib.data_entities.constants import (
    ADDRESS_ZERO, 
    ARB_RETRYABLE_TX_ADDRESS,
    DEFAULT_DEPOSIT_TIMEOUT,
    SEVEN_DAYS_IN_SECONDS
)
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.child_transaction import ChildTransactionReceipt
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import get_address, load_contract
from src.lib.utils.lib import get_transaction_receipt, is_defined


def int_to_bytes(value):
    return Web3.to_bytes(value)


def hex_to_bytes(value):
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def zero_pad(value, length):
    return value.rjust(length, b"\x00")


def format_number(value):
    hex_str = Web3.to_hex(value)[2:].lstrip("0")
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str
    return bytes.fromhex(hex_str)


def concat(*args):
    if len(args) == 1 and isinstance(args[0], (list, tuple)) and not isinstance(args[0], (bytes, bytearray)):
        iterable = args[0]
    else:
        iterable = args
    return b"".join(iterable)


class ParentToChildMessageStatus:
    NOT_YET_CREATED = 1
    CREATION_FAILED = 2
    FUNDS_DEPOSITED_ON_CHILD = 3
    REDEEMED = 4
    EXPIRED = 5


class EthDepositMessageStatus:
    PENDING = 1
    DEPOSITED = 2


class ParentToChildMessage:
    def __init__(
        self,
        chain_id,
        sender,
        message_number,
        parent_base_fee,
        message_data,
    ):
        self.chain_id = chain_id
        self.sender = sender
        self.message_number = message_number
        self.parent_base_fee = parent_base_fee
        self.message_data = message_data
        self.retryable_creation_id = ParentToChildMessage.calculate_submit_retryable_id(
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
        child_chain_id,
        from_address,
        message_number,
        parent_base_fee,
        dest_address,
        child_call_value,
        parent_call_value,
        max_submission_fee,
        excess_fee_refund_address,
        call_value_refund_address,
        gas_limit,
        max_fee_per_gas,
        data,
    ):
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
        chain_signer_or_provider,
        chain_id,
        sender,
        message_number,
        parent_base_fee,
        message_data,
    ):
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
    def __init__(
        self,
        child_provider,
        chain_id,
        sender,
        message_number,
        parent_base_fee,
        message_data,
    ):
        super().__init__(chain_id, sender, message_number, parent_base_fee, message_data)
        self.child_provider = child_provider
        self.retryable_creation_receipt = None

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = await get_transaction_receipt(
                self.child_provider, 
                self.retryable_creation_id, 
                confirmations, 
                timeout
            )
        return self.retryable_creation_receipt or None

    async def get_auto_redeem_attempt(self):
        creation_receipt = await self.get_retryable_creation_receipt()

        if creation_receipt:
            child_receipt = ChildTransactionReceipt(creation_receipt)
            redeem_events = child_receipt.get_redeem_scheduled_events()

            if len(redeem_events) == 1:
                try:
                    return self.child_provider.eth.get_transaction_receipt(redeem_events[0]["retryTxHash"])
                except Exception:
                    pass
            elif len(redeem_events) > 1:
                raise ArbSdkError(
                    f"Unexpected number of redeem events for retryable creation tx. {creation_receipt} {redeem_events}"
                )

        return None

    async def get_successful_redeem(self):
        chainNetwork = get_arbitrum_network(self.child_provider)
        event_fetcher = EventFetcher(self.child_provider)
        creation_receipt = await self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return {"status": ParentToChildMessageStatus.NOT_YET_CREATED}

        if creation_receipt.status == 0:
            return {"status": ParentToChildMessageStatus.CREATION_FAILED}

        auto_redeem = await self.get_auto_redeem_attempt()
        if auto_redeem and auto_redeem.status == 1:
            return {
                "childTxReceipt": auto_redeem, 
                "status": ParentToChildMessageStatus.REDEEMED
            }

        if await self.retryable_exists():
            return {"status": ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD}

        increment = 1000
        from_block = self.child_provider.eth.get_block(creation_receipt.blockNumber)
        timeout = (from_block.timestamp + 
                  (chainNetwork.retryableLifetimeSeconds or SEVEN_DAYS_IN_SECONDS))

        queried_range = []
        max_block = self.child_provider.eth.block_number

        while from_block.number < max_block:
            to_block_number = min(from_block.number + increment, max_block)
            outer_block_range = {"from": from_block.number, "to": to_block_number}
            queried_range.append(outer_block_range)

            redeem_events = await event_fetcher.get_events(
                contract_factory="ArbRetryableTx",
                event_name="RedeemScheduled",
                argument_filters={"retryableCreationId": self.retryable_creation_id},
                filter={
                    "fromBlock": outer_block_range["from"],
                    "toBlock": outer_block_range["to"],
                    "address": ARB_RETRYABLE_TX_ADDRESS,
                },
                
            )

            successful_redeems = []
            for e in redeem_events:
                receipt = await get_transaction_receipt(self.child_provider, e["retryTxHash"])
                if receipt and receipt.status == 1:
                    successful_redeems.append(receipt)

            if len(successful_redeems) > 1:
                raise ArbSdkError(
                    f"Unexpected number of successful redeems for ticket {self.retryable_creation_id}."
                )
            if len(successful_redeems) == 1:
                return {
                    "childTxReceipt": successful_redeems[0],
                    "status": ParentToChildMessageStatus.REDEEMED,
                }

            to_block = self.child_provider.eth.get_block(to_block_number)
            if to_block.timestamp > timeout:
                while queried_range:
                    block_range = queried_range.pop(0)
                    keepalive_events = await event_fetcher.get_events(
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

    async def is_expired(self):
        """@deprecated Will be removed in v3.0.0"""
        return await self.retryable_exists()

    async def retryable_exists(self):
        current_timestamp = (self.child_provider.eth.get_block("latest")).timestamp
        try:
            timeout_timestamp = await self.get_timeout()
            return current_timestamp <= timeout_timestamp
        except ContractCustomError as err:
            if err.data == "0x80698456":  # NoTicketWithID error
                return False
            raise err

    async def status(self):
        return (await self.get_successful_redeem())["status"]

    async def wait_for_status(self, confirmations=None, timeout=None):
        chosen_timeout = timeout if is_defined(timeout) else DEFAULT_DEPOSIT_TIMEOUT

        _retryable_creation_receipt = await self.get_retryable_creation_receipt(
            confirmations, chosen_timeout
        )
        if not _retryable_creation_receipt:
            if confirmations or chosen_timeout:
                raise ArbSdkError(
                    f"Timed out waiting for retryable creation receipt: {self.retryable_creation_id}."
                )
            raise ArbSdkError(
                f"Retryable creation receipt not found {self.retryable_creation_id}."
            )

        return await self.get_successful_redeem()

    @staticmethod
    async def get_lifetime(child_provider):
        arb_retryable = load_contract(
            provider=child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            
        )
        return arb_retryable.functions.getLifetime().call()

    async def get_timeout(self):
        arb_retryable = load_contract(
            provider=self.child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            
        )
        return arb_retryable.functions.getTimeout(self.retryable_creation_id).call()

    def get_beneficiary(self):
        arb_retryable = load_contract(
            provider=self.child_provider,
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            
        )
        return arb_retryable.functions.getBeneficiary(self.retryable_creation_id).call()

class ParentToChildMessageReaderClassic:
    def __init__(self, child_provider, chain_id, message_number):
        self.message_number = message_number
        self.child_provider = child_provider
        self.retryable_creation_id = ParentToChildMessageReaderClassic.calculate_retryable_creation_id(
            chain_id, message_number
        )
        self.auto_redeem_id = ParentToChildMessageReaderClassic.calculate_auto_redeem_id(
            self.retryable_creation_id
        )
        self.child_tx_hash = ParentToChildMessageReaderClassic.calculate_chain_tx_hash(
            self.retryable_creation_id
        )
        self.retryable_creation_receipt = None

    @staticmethod
    def calculate_retryable_creation_id(chain_id, message_number):
        def bit_flip(num):
            return num | 1 << 255

        data = concat(
            zero_pad(int_to_bytes(chain_id), 32),
            zero_pad(int_to_bytes(bit_flip(message_number)), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_auto_redeem_id(retryable_creation_id):
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(1), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_chain_tx_hash(retryable_creation_id):
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(0), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_chain_derived_hash(retryable_creation_id):
        """Calculate chain derived hash"""
        data = concat([
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            # BN 0 meaning Chain TX
            zero_pad(int_to_bytes(0), 32),
        ])
        return Web3.keccak(data).hex()

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        """
        Try to get the receipt for the retryable ticket creation.
        This is the Chain transaction that creates the retryable ticket.
        If confirmations or timeout is provided, this will wait for the ticket to be created
        
        Returns:
            Null if retryable has not been created
        """
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = await get_transaction_receipt(
                self.child_provider, 
                self.retryable_creation_id, 
                confirmations, 
                timeout
            )
        return self.retryable_creation_receipt

    async def status(self):
        """Get the message status"""
        creation_receipt = await self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return ParentToChildMessageStatus.NOT_YET_CREATED

        if creation_receipt.status == 0:
            return ParentToChildMessageStatus.CREATION_FAILED

        chain_derived_hash = ParentToChildMessageReaderClassic.calculate_chain_derived_hash(
            self.retryable_creation_id
        )

        chain_tx_receipt = await get_transaction_receipt(
            self.child_provider, 
            chain_derived_hash
        )

        if chain_tx_receipt and chain_tx_receipt.status == 1:
            return ParentToChildMessageStatus.REDEEMED

        return ParentToChildMessageStatus.EXPIRED

class ParentToChildMessageWriter(ParentToChildMessageReader):
    def __init__(self, chain_signer, chain_id, sender, message_number, parent_base_fee, message_data):
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

    async def redeem(self, overrides=None):
        status = await self.status()
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

            redeem_tx = arb_retryable_tx.functions.redeem(self.retryable_creation_id).transact(overrides)
            tx_receipt = self.chain_signer.provider.eth.wait_for_transaction_receipt(redeem_tx)

            return ChildTransactionReceipt.to_redeem_transaction(
                ChildTransactionReceipt.monkey_patch_wait(tx_receipt),
                self.child_provider
            )
        else:
            raise ArbSdkError(
                f"Cannot redeem as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )

    async def cancel(self, overrides=None):
        status = await self.status()
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

            tx_hash = arb_retryable_tx.functions.cancel(self.retryable_creation_id).transact(overrides)
            return await self.chain_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        else:
            raise ArbSdkError(
                f"Cannot cancel as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )

    async def keep_alive(self, overrides=None):
        status = await self.status()
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

            tx_hash = arb_retryable_tx.functions.keepalive(self.retryable_creation_id).transact(overrides)
            return await self.chain_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        else:
            raise ArbSdkError(
                f"Cannot keep alive as retryable does not exist. Message status: "
                f"{ParentToChildMessageStatus(status).name} must be: "
                f"{ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD.name}."
            )


class EthDepositMessage:
    def __init__(self, child_provider, child_chain_id, message_number, from_address, to_address, value):
        self.child_provider = child_provider
        self.child_chain_id = child_chain_id
        self.message_number = message_number
        self.from_address = from_address
        self.to_address = to_address
        self.value = value
        self.child_tx_hash = self.calculate_deposit_tx_id(
            child_chain_id,
            message_number,
            from_address,
            to_address,
            value
        )
        self.child_tx_receipt = None

    @staticmethod
    def calculate_deposit_tx_id(child_chain_id, message_number, from_address, to_address, value):
        chain_id = child_chain_id
        msg_num = message_number

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(get_address(from_address)[2:]),
            bytes.fromhex(get_address(to_address)[2:]),
            format_number(value),
        ]

        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b"\x64" + rlp_encoded

        tx_id = Web3.keccak(rlp_enc_with_type)
        return tx_id.hex()

    @staticmethod
    async def from_event_components(child_provider, message_number, sender_addr, inbox_message_event_data):
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
    def parse_eth_deposit_data(event_data):
        if isinstance(event_data, bytes):
            event_data = Web3.to_hex(event_data)

        address_end = 2 + 20 * 2
        to_address = get_address("0x" + event_data[2:address_end])
        value_hex = event_data[address_end:]
        if value_hex.startswith("0"):
            value_hex = value_hex.lstrip("0")
        if not value_hex:
            value_hex = "0"

        value = int(value_hex, 16) if value_hex != "0" else 0
        return {"to": to_address, "value": value}

    async def status(self):
        receipt = await get_transaction_receipt(self.child_provider, self.child_tx_hash)
        return (
            EthDepositMessageStatus.DEPOSITED 
            if receipt is not None 
            else EthDepositMessageStatus.PENDING
        )

    async def wait(self, confirmations=None, timeout=None):
        chosen_timeout = timeout if is_defined(timeout) else DEFAULT_DEPOSIT_TIMEOUT

        if not self.child_tx_receipt:
            self.child_tx_receipt = await get_transaction_receipt(
                self.child_provider,
                self.child_tx_hash,
                confirmations,
                chosen_timeout
            )

        return self.child_tx_receipt or None