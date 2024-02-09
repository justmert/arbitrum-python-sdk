import math

import rlp
from web3 import Web3
from web3.exceptions import ContractCustomError

from src.lib.data_entities.constants import ADDRESS_ZERO, ARB_RETRYABLE_TX_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.l2_transaction import L2TransactionReceipt
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
        chain_id,
        sender,
        message_number,
        l1_base_fee,
        message_data,
    ):
        self.chain_id = chain_id
        self.sender = sender
        self.message_number = message_number
        self.l1_base_fee = l1_base_fee
        self.message_data = message_data
        self.retryable_creation_id = L1ToL2Message.calculate_submit_retryable_id(
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
        chain_id = l2_chain_id
        msg_num = message_number
        from_addr = Web3.to_checksum_address(from_address)
        dest_addr = "0x" if dest_address == ADDRESS_ZERO else Web3.to_checksum_address(dest_address)
        call_value_refund_addr = Web3.to_checksum_address(call_value_refund_address)
        excess_fee_refund_addr = Web3.to_checksum_address(excess_fee_refund_address)

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(from_addr[2:]),
            format_number(l1_base_fee),
            format_number(l1_value),
            format_number(max_fee_per_gas),
            format_number(gas_limit),
            bytes.fromhex(dest_addr[2:]) if dest_addr != "0x" else b"",
            format_number(l2_call_value),
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
        l2_signer_or_provider,
        chain_id,
        sender,
        message_number,
        l1_base_fee,
        message_data,
    ):
        if SignerProviderUtils.is_signer(l2_signer_or_provider):
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
        l2_provider,
        chain_id,
        sender,
        message_number,
        l1_base_fee,
        message_data,
    ):
        super().__init__(chain_id, sender, message_number, l1_base_fee, message_data)
        self.l2_provider = l2_provider
        self.retryable_creation_receipt = None

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = await get_transaction_receipt(
                self.l2_provider, self.retryable_creation_id, confirmations, timeout
            )
        return self.retryable_creation_receipt or None

    async def get_auto_redeem_attempt(self):
        creation_receipt = await self.get_retryable_creation_receipt()

        if creation_receipt:
            l2_receipt = L2TransactionReceipt(creation_receipt)

            redeem_events = l2_receipt.get_redeem_scheduled_events(self.l2_provider)

            if len(redeem_events) == 1:
                try:
                    return self.l2_provider.eth.get_transaction_receipt(redeem_events[0]["retryTxHash"])

                except Exception:
                    pass
            elif len(redeem_events) > 1:
                raise ArbSdkError(
                    f"Unexpected number of redeem events for retryable creation tx. {creation_receipt} {redeem_events}"
                )

        return None

    async def get_successful_redeem(self):
        l2_network = get_l2_network(self.l2_provider)
        event_fetcher = EventFetcher(self.l2_provider)
        creation_receipt = await self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return {"status": L1ToL2MessageStatus.NOT_YET_CREATED}

        if creation_receipt.status == 0:
            return {"status": L1ToL2MessageStatus.CREATION_FAILED}

        auto_redeem = await self.get_auto_redeem_attempt()

        if auto_redeem and auto_redeem.status == 1:
            return {"l2TxReceipt": auto_redeem, "status": L1ToL2MessageStatus.REDEEMED}

        if await self.retryable_exists():
            return {"status": L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2}

        increment = 1000

        from_block = self.l2_provider.eth.get_block(creation_receipt.blockNumber)

        timeout = from_block.timestamp + l2_network.retryable_lifetime_seconds

        queried_range = []
        max_block = self.l2_provider.eth.block_number

        while from_block.number < max_block:
            to_block_number = min(from_block.number + increment, max_block)

            outer_block_range = {"from": from_block.number, "to": to_block_number}

            queried_range.append(outer_block_range)

            redeem_events = await event_fetcher.get_events(
                contract_factory="ArbRetryableTx",
                event_name="RedeemScheduled",
                argument_filters={"ticketId": self.retryable_creation_id},
                filter={
                    "fromBlock": outer_block_range["from"],
                    "toBlock": outer_block_range["to"],
                    "address": ARB_RETRYABLE_TX_ADDRESS,
                },
                is_classic=False,
            )

            reedems = [await get_transaction_receipt(self.l2_provider, e.event["retryTxHash"]) for e in redeem_events]

            successful_redeems = [r for r in reedems if r is not None and r.status == 1]

            if len(successful_redeems) > 1:
                raise ArbSdkError(
                    f"Unexpected number of successful redeems. Expected only one redeem for ticket {self.retryable_creation_id}, but found {len(successful_redeems)}."
                )

            if len(successful_redeems) == 1:
                return {
                    "l2TxReceipt": successful_redeems[0],
                    "status": L1ToL2MessageStatus.REDEEMED,
                }

            to_block = self.l2_provider.eth.get_block(to_block_number)
            if to_block.timestamp > timeout:
                while len(queried_range) > 0:
                    block_range = queried_range.pop(0)

                    keep_alive_events = await event_fetcher.get_events(
                        contract_factory="ArbRetryableTx",
                        event_name="LifetimeExtended",
                        argument_filters={"retryableCreationId": self.retryable_creation_id},
                        filter={
                            "fromBlock": block_range["from"],
                            "toBlock": block_range["to"],
                            "address": ARB_RETRYABLE_TX_ADDRESS,
                        },
                        is_classic=False,
                    )

                    if len(keep_alive_events) > 0:
                        timeout = sorted(
                            [e.event["newTimeout"] for e in keep_alive_events],
                            reverse=True,
                        )[0]
                        break

                if to_block.timestamp > timeout:
                    break

                while len(queried_range) > 1:
                    queried_range.pop(0)

            processed_seconds = to_block.timestamp - from_block.timestamp
            if processed_seconds != 0:
                increment = math.ceil((increment * 86400) / processed_seconds)

            from_block = to_block

        return {"status": L1ToL2MessageStatus.EXPIRED}

    async def is_expired(self):
        return await self.retryable_exists()

    async def retryable_exists(self):
        current_timestamp = (self.l2_provider.eth.get_block("latest")).timestamp
        try:
            timeout_timestamp = await self.get_timeout()
            return current_timestamp <= timeout_timestamp

        except ContractCustomError as err:
            if err.data == "0x80698456":
                return False

        except Exception as err:
            raise err

    async def status(self):
        return (await self.get_successful_redeem())["status"]

    async def wait_for_status(self, confirmations=None, timeout=None):
        l2_network = get_l2_network(self.chain_id)

        chosen_timeout = timeout if timeout is not None else l2_network["depositTimeout"]

        _retryable_creation_receipt = await self.get_retryable_creation_receipt(confirmations, chosen_timeout)

        if not _retryable_creation_receipt:
            if confirmations or chosen_timeout:
                raise ArbSdkError(
                    f"Timed out waiting to retrieve retryable creation receipt: {self.retryable_creation_id}."
                )
            else:
                raise ArbSdkError(f"Retryable creation receipt not found {self.retryable_creation_id}.")

        return await self.get_successful_redeem()

    @staticmethod
    async def get_lifetime(l2_provider):
        arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            provider=l2_provider,
            is_classic=False,
        )
        return arb_retryable_tx_contract.functions.getLifetime().call()

    async def get_timeout(self):
        arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            provider=self.l2_provider,
            is_classic=False,
        )
        return arb_retryable_tx_contract.functions.getTimeout(self.retryable_creation_id).call()

    async def get_beneficiary(self):
        arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx",
            address=ARB_RETRYABLE_TX_ADDRESS,
            provider=self.l2_provider,
            is_classic=False,
        )
        return arb_retryable_tx_contract.functions.getBeneficiary(self.retryable_creation_id).call()


class L1ToL2MessageReaderClassic:
    def __init__(self, l2_provider, chain_id, message_number):
        self.message_number = message_number
        self.l2_provider = l2_provider
        self.retryable_creation_id = L1ToL2MessageReaderClassic.calculate_retryable_creation_id(
            chain_id, message_number
        )
        self.auto_redeem_id = L1ToL2MessageReaderClassic.calculate_auto_redeem_id(self.retryable_creation_id)
        self.l2_tx_hash = L1ToL2MessageReaderClassic.calculate_l2_tx_hash(self.retryable_creation_id)
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
    def calculate_l2_tx_hash(retryable_creation_id):
        data = concat(
            zero_pad(hex_to_bytes(retryable_creation_id), 32),
            zero_pad(int_to_bytes(0), 32),
        )
        return Web3.keccak(data).hex()

    @staticmethod
    def calculate_l2_derived_hash(retryable_creation_id):
        data = concat(
            [
                zero_pad(hex_to_bytes(retryable_creation_id), 32),
                zero_pad(int_to_bytes(0), 32),
            ]
        )
        return Web3.keccak(data).hex()

    async def get_retryable_creation_receipt(self, confirmations=None, timeout=None):
        if not self.retryable_creation_receipt:
            self.retryable_creation_receipt = await get_transaction_receipt(
                self.l2_provider, self.retryable_creation_id, confirmations, timeout
            )
        return self.retryable_creation_receipt

    async def status(self):
        creation_receipt = await self.get_retryable_creation_receipt()

        if not is_defined(creation_receipt):
            return L1ToL2MessageStatus.NOT_YET_CREATED

        if creation_receipt.status == 0:
            return L1ToL2MessageStatus.CREATION_FAILED

        l2_derived_hash = L1ToL2MessageReaderClassic.calculate_l2_derived_hash(self.retryable_creation_id)

        l2_tx_receipt = await get_transaction_receipt(self.l2_provider, l2_derived_hash)

        if l2_tx_receipt and l2_tx_receipt.status == 1:
            return L1ToL2MessageStatus.REDEEMED

        return L1ToL2MessageStatus.EXPIRED


class L1ToL2MessageWriter(L1ToL2MessageReader):
    def __init__(self, l2_signer, chain_id, sender, message_number, l1_base_fee, message_data):
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
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.l2_signer.provider,
                is_classic=False,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.l2_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]

            redeem_hash = arb_retryable_tx.functions.redeem(self.retryable_creation_id).transact(overrides)

            tx_receipt = self.l2_signer.provider.eth.wait_for_transaction_receipt(redeem_hash)

            return L2TransactionReceipt.to_redeem_transaction(
                L2TransactionReceipt.monkey_patch_wait(tx_receipt), self.l2_provider
            )
        else:
            raise ArbSdkError(
                f"Cannot redeem as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )

    async def cancel(self, overrides=None):
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.l2_signer.provider,
                is_classic=False,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.l2_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]
            tx_hash = await arb_retryable_tx.functions.cancel(self.retryable_creation_id).transact(overrides)

            receipt = await self.l2_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

            return receipt
        else:
            raise ArbSdkError(
                f"Cannot cancel as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )

    async def keep_alive(self, overrides=None):
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx",
                address=ARB_RETRYABLE_TX_ADDRESS,
                provider=self.l2_signer.provider,
                is_classic=False,
            )

            if overrides is None:
                overrides = {}

            if "from" not in overrides:
                overrides["from"] = self.l2_signer.account.address

            if "gasLimit" in overrides:
                overrides["gas"] = overrides.pop("gasLimit")
                if not overrides["gas"]:
                    del overrides["gas"]
                    
            keepalive_tx = await arb_retryable_tx.functions.keepalive(self.retryable_creation_id).transact(overrides)

            receipt = await self.l2_signer.provider.eth.wait_for_transaction_receipt(keepalive_tx)

            return receipt
        else:
            raise ArbSdkError(
                f"Cannot keep alive as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )


class EthDepositMessage:
    def __init__(self, l2_provider, l2_chain_id, message_number, from_address, to_address, value):
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
    def calculate_deposit_tx_id(l2_chain_id, message_number, from_address, to_address, value):
        chain_id = l2_chain_id
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

        retryable_tx_id = Web3.keccak(rlp_enc_with_type)
        return retryable_tx_id.hex()

    @staticmethod
    def from_event_components(l2_provider, message_number, sender_addr, inbox_message_event_data):
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
        if isinstance(event_data, bytes):
            event_data = Web3.to_hex(event_data)

        address_end = 2 + 20 * 2
        to_address = get_address("0x" + event_data[2:address_end])
        value_hex = event_data[address_end:]
        if value_hex.startswith("0"):
            value_hex = value_hex.lstrip("0")

        value = int("0x" + value_hex, 16)
        return {"to": to_address, "value": value}

    async def status(self):
        receipt = await get_transaction_receipt(self.l2_provider, self.l2_deposit_tx_hash)
        if receipt is None:
            return "PENDING"
        else:
            return "DEPOSITED"

    async def wait(self, confirmations=None, timeout=None):
        l2_network = get_l2_network(self.l2_chain_id)

        chosen_timeout = timeout if is_defined(timeout) else l2_network["depositTimeout"]

        if not self.l2_deposit_tx_receipt:
            self.l2_deposit_tx_receipt = await get_transaction_receipt(
                self.l2_provider, self.l2_deposit_tx_hash, confirmations, chosen_timeout
            )

        return self.l2_deposit_tx_receipt or None
