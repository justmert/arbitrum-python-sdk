from web3 import Web3
from eth_utils import keccak, to_checksum_address, encode_hex
from web3.types import TxReceipt
from typing import Union, Optional, Dict
import web3
from web3 import Web3
from eth_typing import ChecksumAddress
from eth_utils import keccak, encode_hex
import asyncio
from web3.exceptions import TransactionNotFound
import rlp
from eth_utils import keccak, to_bytes, to_checksum_address, pad_left
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.utils.event_fetcher import EventFetcher
import math
from src.lib.data_entities.constants import ARB_RETRYABLE_TX_ADDRESS
from web3.contract import Contract
from src.lib.utils.helper import load_contract
from eth_utils import keccak, to_bytes, pad_left
from src.lib.message.l2_transaction import L2TransactionReceipt
# Additional imports and utility functions might be required.


def int_to_bytes(value: int) -> bytes:
    return to_bytes(value)


def hex_to_bytes(value: str) -> bytes:
    # Remove '0x' prefix if present and convert to bytes
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def zero_pad(value: bytes, length: int) -> bytes:
    # Pad the value to the left to make it the specified length
    return pad_left(value, length, b"\0")


def concat(*args) -> bytes:
    # Concatenate all byte arguments
    return b"".join(args)


class L1ToL2MessageStatus:
    NOT_YET_CREATED = 1
    CREATION_FAILED = 2
    FUNDS_DEPOSITED_ON_L2 = 3
    REDEEMED = 4
    EXPIRED = 5


class EthDepositStatus:
    PENDING = 1
    DEPOSITED = 2


class L1ToL2Message:
    def __init__(
        self,
        chain_id: int,
        sender: str,
        message_number: int,
        l1_base_fee: int,
        message_data: Dict,
    ):
        self.chain_id = chain_id
        self.sender = sender
        self.message_number = message_number
        self.l1_base_fee = l1_base_fee
        self.message_data = message_data
        self.retryable_creation_id = self.calculate_submit_retryable_id(
            chain_id,
            sender,
            message_number,
            l1_base_fee,
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
        l2_chain_id,
        from_address,
        message_number,
        l1_base_fee,
        dest_address,
        l2_call_value,
        l1_value,
        max_submission_fee,
        excess_fee_refund_address,
        call_value_refund_address,
        gas_limit,
        max_fee_per_gas,
        data,
    ):
        def format_number(value):
            return to_bytes(value)

        chain_id = format_number(l2_chain_id)
        msg_num = format_number(message_number)

        fields = [
            pad_left(chain_id, 32, b"\0"),
            pad_left(msg_num, 32, b"\0"),
            to_checksum_address(from_address),
            format_number(l1_base_fee),
            format_number(l1_value),
            format_number(max_fee_per_gas),
            format_number(gas_limit),
            "0x"
            if dest_address == Web3.toChecksumAddress("0x0")
            else to_checksum_address(dest_address),
            format_number(l2_call_value),
            to_checksum_address(call_value_refund_address),
            format_number(max_submission_fee),
            to_checksum_address(excess_fee_refund_address),
            data.encode("utf-8") if isinstance(data, str) else data,
        ]

        # RLP encode the fields and prepend the type byte (0x69 for Arbitrum submit retry transactions)
        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b"\x69" + rlp_encoded

        # Compute the keccak256 hash
        return keccak(rlp_enc_with_type).hex()

    @staticmethod
    def from_event_components(
        l2_signer_or_provider,
        chain_id,
        sender,
        message_number,
        l1_base_fee,
        message_data,
    ):
        if SignerProviderUtils.is_signer(
            l2_signer_or_provider
        ):  # Signer is a hypothetical class; replace with actual signer type
            return L1ToL2MessageWriter(
                l2_signer_or_provider,
                chain_id,
                sender,
                message_number,
                l1_base_fee,
                message_data,
            )
        else:
            return L1ToL2MessageReader(
                l2_signer_or_provider,
                chain_id,
                sender,
                message_number,
                l1_base_fee,
                message_data,
            )


class L1ToL2MessageReader(L1ToL2Message):
    def __init__(
        self,
        l2_provider: Web3,
        chain_id: int,
        sender: str,
        message_number: int,
        l1_base_fee: int,
        message_data: Dict,
    ):
        super().__init__(chain_id, sender, message_number, l1_base_fee, message_data)
        self.l2_provider = l2_provider
        self.retryable_creation_receipt = None

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = (
                self.l2_provider.eth.get_transaction_receipt(
                    self.l2_provider, self.retryable_creation_id, confirmations, timeout
                )
            )

        return self.retryable_creation_receipt or None

    async def get_auto_redeem_attempt(self) -> Optional[TxReceipt]:
        creation_receipt = await self.get_retryable_creation_receipt()
        if creation_receipt:
            l2_receipt = L2TransactionReceipt(
                creation_receipt
            )  # Assuming L2TransactionReceipt is implemented
            redeem_events = l2_receipt.get_redeem_scheduled_events()

            if len(redeem_events) == 1:
                return await self.l2_provider.eth.get_transaction_receipt(
                    redeem_events[0]["retryTxHash"]
                )
            elif len(redeem_events) > 1:
                raise ArbSdkError(
                    f"Unexpected number of redeem events for retryable creation tx: {len(redeem_events)}"
                )

        return None

    async def get_successful_redeem(self):
        l2_network = get_l2_network(self.l2_provider)
        creation_receipt = await self.get_retryable_creation_receipt()

        if not creation_receipt:
            return {"status": L1ToL2MessageStatus.NOT_YET_CREATED}

        if creation_receipt.status == 0:
            return {"status": L1ToL2MessageStatus.CREATION_FAILED}

        auto_redeem = await self.get_auto_redeem_attempt()
        if auto_redeem and auto_redeem.status == 1:
            return {"l2TxReceipt": auto_redeem, "status": L1ToL2MessageStatus.REDEEMED}

        if await self.retryable_exists():
            return {"status": L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2}

        increment = 1000
        from_block = creation_receipt.blockNumber
        max_block = self.l2_provider.eth.block_number
        timeout = from_block.timestamp + l2_network.retryable_lifetime_seconds
        queried_range = []

        while from_block.number < max_block:
            to_block_number = min(from_block.number + increment, max_block)
            outer_block_range = {"from": from_block.number, "to": to_block_number}
            queried_range.append(outer_block_range)

            arb_retryable_tx_contract = self.l2_provider.eth.contract(
                address=Web3.toChecksumAddress(ARB_RETRYABLE_TX_ADDRESS),
                abi=self.arb_retryable_tx_abi,
            )

            redeem_filter = (
                arb_retryable_tx_contract.events.RedeemScheduled.createFilter(
                    fromBlock=outer_block_range["from"],
                    toBlock=outer_block_range["to"],
                    argument_filters={
                        "retryableCreationId": self.retryable_creation_id
                    },
                )
            )
            redeem_events = redeem_filter.get_all_entries()

            for event in redeem_events:
                receipt = self.l2_provider.eth.get_transaction_receipt(
                    event["retryTxHash"]
                )
                if receipt and receipt.status == 1:
                    return {
                        "l2TxReceipt": receipt,
                        "status": L1ToL2MessageStatus.REDEEMED,
                    }

            to_block = await self.l2_provider.eth.get_block(to_block_number)
            if to_block.timestamp > timeout:
                while queried_range:
                    block_range = queried_range.pop(0)
                    lifetime_extended_filter = (
                        arb_retryable_tx_contract.events.LifetimeExtended.createFilter(
                            fromBlock=block_range["from"],
                            toBlock=block_range["to"],
                            argument_filters={
                                "retryableCreationId": self.retryable_creation_id
                            },
                        )
                    )
                    lifetime_extended_events = (
                        lifetime_extended_filter.get_all_entries()
                    )

                    if lifetime_extended_events:
                        new_timeout = max(
                            e["newTimeout"] for e in lifetime_extended_events
                        )
                        if new_timeout > timeout:
                            timeout = new_timeout
                            break

                if to_block.timestamp > timeout:
                    break

            processed_seconds = to_block.timestamp - from_block.timestamp
            if processed_seconds != 0:
                increment = math.ceil((increment * 86400) / processed_seconds)

            from_block = to_block

        return {"status": L1ToL2MessageStatus.EXPIRED}

    async def is_expired(self) -> bool:
        return await self.retryable_exists()

    async def retryable_exists(self) -> bool:
        current_timestamp = (await self.l2_provider.eth.get_block("latest")).timestamp
        try:
            timeout_timestamp = await self.get_timeout()
            return current_timestamp <= timeout_timestamp
        except Exception as err:
            # Assuming RetryableExistsError is a custom exception you define for handling specific error cases
            # if isinstance(err, RetryableExistsError) and err.code == Logger.errors.CALL_EXCEPTION and err.error_name == 'NoTicketWithID':
            #     return False
            raise err

    async def status(self) -> int:
        return (await self.get_successful_redeem())["status"]

    async def wait_for_status(
        self, confirmations: Optional[int] = None, timeout: Optional[int] = None
    ) -> Dict[str, Union[int, Optional[TxReceipt]]]:
        l2_network = await get_l2_network(
            self.chain_id
        )  # Assuming get_l2_network is implemented

        chosen_timeout = (
            timeout if timeout is not None else l2_network["deposit_timeout"]
        )

        _retryable_creation_receipt = await self.get_retryable_creation_receipt(
            confirmations, chosen_timeout
        )
        if _retryable_creation_receipt is None:
            if confirmations or chosen_timeout:
                raise ArbSdkError(
                    f"Timed out waiting to retrieve retryable creation receipt: {self.retryable_creation_id}."
                )
            else:
                raise ArbSdkError(
                    f"Retryable creation receipt not found {self.retryable_creation_id}."
                )

        return await self.get_successful_redeem()

    @staticmethod
    async def get_lifetime(l2_provider):
        arb_retryable_tx_contract = load_contract(
            "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, l2_provider
        )
        return await arb_retryable_tx_contract.functions.getLifetime().call()

    async def get_timeout(self):
        arb_retryable_tx_contract = load_contract(
            "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, self.l2_provider
        )
        return await arb_retryable_tx_contract.functions.getTimeout(
            self.retryable_creation_id
        ).call()

    async def get_beneficiary(self):
        arb_retryable_tx_contract = load_contract(
            "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, self.l2_provider
        )
        return await arb_retryable_tx_contract.functions.getBeneficiary(
            self.retryable_creation_id
        ).call()


class L1ToL2MessageReaderClassic:
    def __init__(self, l2_provider, chain_id, message_number):
        self.message_number = message_number
        self.l2_provider = l2_provider
        self.retryable_creation_id = self._calculate_retryable_creation_id(
            chain_id, message_number
        )
        self.auto_redeem_id = self._calculate_auto_redeem_id(self.retryable_creation_id)
        self.l2_tx_hash = self._calculate_l2_tx_hash(self.retryable_creation_id)
        self.retryable_creation_receipt = None

    def calculate_retryable_creation_id(chain_id: int, message_number: int) -> str:
        bit_flip = lambda num: num | (1 << 255)
        data = concat(
            zero_pad(int_to_bytes(chain_id), 32),
            zero_pad(int_to_bytes(bit_flip(message_number)), 32),
        )
        return keccak(data).hex()

    def calculate_auto_redeem_id(retryable_creation_id: str) -> str:
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(1), 32),
        )
        return keccak(data).hex()

    def calculate_l2_tx_hash(retryable_creation_id: str) -> str:
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(0), 32),
        )
        return keccak(data).hex()

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        if self.retryable_creation_receipt is None:
            self.retryable_creation_receipt = (
                await self.l2_provider.eth.get_transaction_receipt(
                    self.l2_provider, self.retryable_creation_id, confirmations, timeout
                )
            )
        return self.retryable_creation_receipt

    async def status(self):
        creation_receipt = await self.get_retryable_creation_receipt()
        if not creation_receipt:
            return L1ToL2MessageStatus.NOT_YET_CREATED
        if creation_receipt.status == 0:
            return L1ToL2MessageStatus.CREATION_FAILED
        l2_tx_receipt = await self.l2_provider.eth.get_transaction_receipt(
            self.l2_tx_hash
        )
        if l2_tx_receipt and l2_tx_receipt.status == 1:
            return L1ToL2MessageStatus.REDEEMED
        return L1ToL2MessageStatus.EXPIRED


class L1ToL2MessageWriter(L1ToL2MessageReader):
    def __init__(
        self, l2_signer, chain_id, sender, message_number, l1_base_fee, message_data
    ):
        super().__init__(
            l2_signer.provider,
            chain_id,
            sender,
            message_number,
            l1_base_fee,
            message_data,
        )
        if not l2_signer.provider:
            raise ArbSdkError("Signer not connected to provider.")
        self.l2_signer = l2_signer

    async def redeem(self, overrides=None):
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            # Load the ArbRetryableTx contract
            arb_retryable_tx = load_contract(
                "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, self.l2_signer
            )

            # Send the redeem transaction
            redeem_tx = await arb_retryable_tx.functions.redeem(
                self.retryable_creation_id
            ).transact(overrides or {})

            # Wait for the transaction receipt
            receipt = await self.l2_signer.provider.eth.wait_for_transaction_receipt(
                redeem_tx
            )

            # Apply monkey patch to the transaction receipt
            monkey_patched_receipt = L2TransactionReceipt.monkey_patch_wait(receipt)

            # Convert the monkey patched receipt to a redeem transaction
            redeem_transaction = L2TransactionReceipt.to_redeem_transaction(
                monkey_patched_receipt, self.l2_provider
            )

            return redeem_transaction
        else:
            raise ArbSdkError(
                f"Cannot redeem as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )

    async def cancel(self, overrides=None):
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            # Load the ArbRetryableTx contract
            arb_retryable_tx = load_contract(
                "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, self.l2_signer
            )

            # Send the cancel transaction
            cancel_tx = await arb_retryable_tx.functions.cancel(
                self.retryable_creation_id
            ).transact(overrides or {})

            # Wait for the transaction receipt
            receipt = await self.l2_signer.provider.eth.wait_for_transaction_receipt(
                cancel_tx
            )

            return receipt
        else:
            raise ArbSdkError(
                f"Cannot cancel as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )

    async def keep_alive(self, overrides=None):
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            # Load the ArbRetryableTx contract
            arb_retryable_tx = load_contract(
                "ArbRetryableTx", ARB_RETRYABLE_TX_ADDRESS, self.l2_signer
            )

            # Send the keepalive transaction
            keepalive_tx = await arb_retryable_tx.functions.keepalive(
                self.retryable_creation_id
            ).transact(overrides or {})

            # Wait for the transaction receipt
            receipt = await self.l2_signer.provider.eth.wait_for_transaction_receipt(
                keepalive_tx
            )

            return receipt
        else:
            raise ArbSdkError(
                f"Cannot keep alive as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )


class EthDepositMessage:
    def __init__(
        self, l2_provider, l2_chain_id, message_number, from_address, to_address, value
    ):
        self.l2_provider = l2_provider
        self.l2_chain_id = l2_chain_id
        self.message_number = message_number
        self.from_address = from_address
        self.to_address = to_address
        self.value = value
        self.l2_deposit_tx_hash = self.calculate_deposit_tx_id(
            l2_chain_id, message_number, from_address, to_address, value
        )
        self.l2_deposit_tx_receipt = None

    @staticmethod
    def calculate_deposit_tx_id(
        l2_chain_id, message_number, from_address, to_address, value
    ):
        chain_id = Web3.toBytes(l2_chain_id).rjust(32, b"\0")
        msg_num = Web3.toBytes(message_number).rjust(32, b"\0")
        from_addr = Web3.toBytes(hexstr=Web3.toChecksumAddress(from_address))
        to_addr = Web3.toBytes(hexstr=Web3.toChecksumAddress(to_address))
        value_bytes = Web3.toBytes(value).rjust(32, b"\0")

        fields = [chain_id, msg_num, from_addr, to_addr, value_bytes]

        rlp_encoded = Web3.encode_rlp(fields)
        rlp_encoded_with_type = b"\x64" + rlp_encoded

        return encode_hex(keccak(rlp_encoded_with_type))

    @staticmethod
    def from_event_components(
        l2_provider, message_number, sender_addr, inbox_message_event_data
    ):
        chain_id = l2_provider.eth.chain_id
        parsed_data = EthDepositMessage.parse_eth_deposit_data(inbox_message_event_data)
        return EthDepositMessage(
            l2_provider,
            chain_id,
            message_number,
            sender_addr,
            parsed_data["to"],
            parsed_data["value"],
        )

    @staticmethod
    def parse_eth_deposit_data(event_data):
        address_end = 2 + 20 * 2
        to_address = Web3.toChecksumAddress("0x" + event_data[2:address_end])
        value = Web3.toBytes(hexstr="0x" + event_data[address_end:])
        return {"to": to_address, "value": value}

    async def status(self):
        receipt = await self.l2_provider.eth.get_transaction_receipt(
            self.l2_deposit_tx_hash
        )
        if receipt is None:
            return "PENDING"
        else:
            return "DEPOSITED"

    async def wait(self, confirmations=None, timeout=None):
        # Get the L2 network information
        l2_network = get_l2_network(self.l2_chain_id)

        # Set the chosen timeout based on the provided timeout or the network's default deposit timeout
        chosen_timeout = (
            timeout if timeout is not None else l2_network["depositTimeout"]
        )

        # Start time for timeout calculation
        start_time = asyncio.get_event_loop().time()

        # Loop until the transaction is confirmed or the timeout is reached
        while True:
            try:
                # Attempt to get the transaction receipt
                self.l2_deposit_tx_receipt = (
                    await self.l2_provider.eth.get_transaction_receipt(
                        self.l2_deposit_tx_hash
                    )
                )

                # Check if the number of confirmations is met
                current_block = await self.l2_provider.eth.block_number
                if (
                    confirmations is None
                    or current_block - self.l2_deposit_tx_receipt.blockNumber
                    >= confirmations
                ):
                    return self.l2_deposit_tx_receipt

            except TransactionNotFound:
                # If the transaction is not found, continue the loop
                pass

            # Check if the timeout is reached
            if asyncio.get_event_loop().time() - start_time > chosen_timeout:
                raise TimeoutError(
                    f"Timeout reached waiting for transaction receipt: {self.l2_deposit_tx_hash}"
                )

            # Wait a short time before trying again
            await asyncio.sleep(5)
