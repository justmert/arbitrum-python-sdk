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
from eth_utils import keccak, to_bytes, to_checksum_address
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_l2_network
from src.lib.utils.event_fetcher import EventFetcher
import math
from src.lib.data_entities.constants import ARB_RETRYABLE_TX_ADDRESS
from web3.contract import Contract
from src.lib.utils.helper import get_address, load_contract
from eth_utils import keccak, to_bytes
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.utils.lib import get_transaction_receipt
# Additional imports and utility functions might be required.
from eth_utils import to_checksum_address, keccak, to_bytes
from web3.exceptions import ContractCustomError

def int_to_bytes(value: int) -> bytes:
    return to_bytes(value)


def hex_to_bytes(value: str) -> bytes:
    # Remove '0x' prefix if present and convert to bytes
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


# # Define your own zero padding function
# def zero_pad(value: bytes, length: int) -> bytes:
#     return value.rjust(length, b'\0')



def zero_pad(value, length):
    # Pad the value to the required length
    return value.rjust(length, b'\x00')

def format_number(value):
    hex_str = Web3.to_hex(value)[2:].lstrip('0')

    # Ensure the hex string has an even number of characters
    if len(hex_str) % 2 != 0:
        hex_str = '0' + hex_str
    return bytes.fromhex(hex_str)


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
        print('***************')
        print(
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
        print('***************')
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
    def normalize_address(dest_address):
        # Check if the destination address is the zero address
        if dest_address.lower() == "0x0" or dest_address.lower() == "0x" + "0" * 40:
            return "0x"
        else:
            return Web3.to_checksum_address(dest_address)

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
        from_addr = to_checksum_address(from_address)
        dest_addr = "0x" if dest_address == "0x0000000000000000000000000000000000000000" else to_checksum_address(dest_address)
        call_value_refund_addr = to_checksum_address(call_value_refund_address)
        excess_fee_refund_addr = to_checksum_address(excess_fee_refund_address)

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(from_addr[2:]),
            format_number(l1_base_fee),
            format_number(l1_value),
            format_number(max_fee_per_gas),
            format_number(gas_limit),
            bytes.fromhex(dest_addr[2:]) if dest_addr != '0x' else b'',
            format_number(l2_call_value),
            bytes.fromhex(call_value_refund_addr[2:]),
            format_number(max_submission_fee),
            bytes.fromhex(excess_fee_refund_addr[2:]),
            bytes.fromhex(data[2:]),
        ]

        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b'\x69' + rlp_encoded

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
            print('BURAYA GIRIYOIR!', self.retryable_creation_id)
            self.retryable_creation_receipt = (
                await get_transaction_receipt(
                    self.l2_provider, self.retryable_creation_id, confirmations, timeout
                )
            )
            print('sonuc', self.retryable_creation_receipt)

        return self.retryable_creation_receipt or None

    async def get_auto_redeem_attempt(self) -> Optional[TxReceipt]:
        creation_receipt = await self.get_retryable_creation_receipt()
        if creation_receipt:
            l2_receipt = L2TransactionReceipt(
                creation_receipt
            )  # Assuming L2TransactionReceipt is implemented
            redeem_events = l2_receipt.get_redeem_scheduled_events(self.l2_provider)
            print("reedem_events", redeem_events)
            if len(redeem_events) == 1:
                return await get_transaction_receipt( self.l2_provider,
                    redeem_events[0]["retryTxHash"]
                )
            elif len(redeem_events) > 1:
                raise ArbSdkError(
                    f"Unexpected number of redeem events for retryable creation tx: {len(redeem_events)}"
                )

        return None

    async def get_successful_redeem(self):
        print('***********************get_successful_redeem entered')
        l2_network = get_l2_network(self.l2_provider)
        creation_receipt = await self.get_retryable_creation_receipt()
        print('creation_receipt', creation_receipt)
        if not creation_receipt:
            print('a-NOT_YET_CREATED')
            return {"status": L1ToL2MessageStatus.NOT_YET_CREATED}

        if creation_receipt.status == 0:
            print('b-CREATION_FAILED')
            return {"status": L1ToL2MessageStatus.CREATION_FAILED}

        auto_redeem = await self.get_auto_redeem_attempt()
        print('auto_redeem', auto_redeem)
        if auto_redeem and auto_redeem.status == 1:
            print('c-REDEEMED')
            return {"l2TxReceipt": auto_redeem, "status": L1ToL2MessageStatus.REDEEMED}

        if await self.retryable_exists():
            print('d-FUNDS_DEPOSITED_ON_L2')
            return {"status": L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2}

        increment = 1000
        from_block_number = creation_receipt.blockNumber
        max_block = self.l2_provider.eth.block_number
            
        from_block = self.l2_provider.eth.get_block(from_block_number)
        timeout = from_block.timestamp + l2_network.retryable_lifetime_seconds

        queried_range = []

        while from_block.number < max_block:
            to_block_number = min(from_block.number + increment, max_block)
            outer_block_range = {"from": from_block.number, "to": to_block_number}
            queried_range.append(outer_block_range)

            arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_provider, is_classic=False
        )
            
            print("retry_id", self.retryable_creation_id)
            redeem_filter = (
                arb_retryable_tx_contract.events.RedeemScheduled.create_filter(
                    fromBlock=outer_block_range["from"],
                    toBlock=outer_block_range["to"],
                    address=ARB_RETRYABLE_TX_ADDRESS,
                    argument_filters={
                        "ticketId": self.retryable_creation_id
                    },
                )
            )
            
            redeem_events = redeem_filter.get_all_entries()
            print('reedem_events', redeem_events)
            for event in redeem_events:
                print('event', event)
                receipt = await get_transaction_receipt(self.l2_provider,
                    event.args["retryTxHash"]
                )
                print('receipt', receipt)
                if receipt and receipt.status == 1:
                    print('e-REDEEMED')
                    return {
                        "l2TxReceipt": receipt,
                        "status": L1ToL2MessageStatus.REDEEMED,
                    }

            to_block = self.l2_provider.eth.get_block(to_block_number)
            if to_block.timestamp > timeout:
                while queried_range:
                    block_range = queried_range.pop(0)
                    lifetime_extended_filter = (
                        arb_retryable_tx_contract.events.LifetimeExtended.create_filter(
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

        print('f-EXPIRED')
        print('***********************get_successful_redeem exited')
        return {"status": L1ToL2MessageStatus.EXPIRED}

    async def is_expired(self) -> bool:
        return await self.retryable_exists()

    async def retryable_exists(self) -> bool:
        current_timestamp = (self.l2_provider.eth.get_block("latest")).timestamp
        try:
            timeout_timestamp = await self.get_timeout()
            print("timeout", type(timeout_timestamp))
            print("current",type(current_timestamp))
            print(current_timestamp <= timeout_timestamp)
            return current_timestamp <= timeout_timestamp
        
        except ContractCustomError as err:
            if (err.data == "0x80698456"):
                print("bura")
                return False

        except Exception as err:

            #       if (
            #     err instanceof Error &&
            #     (err as unknown as RetryableExistsError).code ===
            #     Logger.errors.CALL_EXCEPTION &&
            #     (err as unknown as RetryableExistsError).errorName === 'NoTicketWithID'
            # ) {
            #     return false
            # }
            # throw err
            print("err", err)
            print(err.args)
            print(err.data)
            print('BURADAYIM    ')
            # exit()

            # Assuming RetryableExistsError is a custom exception you define for handling specific error cases
            # if isinstance(err, RetryableExistsError) and err.code == Logger.errors.CALL_EXCEPTION and err.error_name == 'NoTicketWithID':
            #     return False
            raise err

    async def status(self) -> int:
        return (await self.get_successful_redeem())["status"]

    async def wait_for_status(
        self, confirmations: Optional[int] = None, timeout: Optional[int] = None
    ) -> Dict[str, Union[int, Optional[TxReceipt]]]:
        l2_network = get_l2_network(
            self.chain_id
        )  # Assuming get_l2_network is implemented

        chosen_timeout = (
            timeout if timeout is not None else l2_network["deposit_timeout"]
        )
        print('chosen_timeout', chosen_timeout)

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
            contract_name="ArbRetryableTx",address= ARB_RETRYABLE_TX_ADDRESS, provider=l2_provider, is_classic=False
        )
        return arb_retryable_tx_contract.functions.getLifetime().call()

    async def get_timeout(self):
        arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_provider, is_classic=False
        )
        return arb_retryable_tx_contract.functions.getTimeout(
            self.retryable_creation_id
        ).call()

    async def get_beneficiary(self):
        arb_retryable_tx_contract = load_contract(
            contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_provider, is_classic=False
        )
        return arb_retryable_tx_contract.functions.getBeneficiary(
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
                await get_transaction_receipt(
                    self.l2_provider, self.retryable_creation_id, confirmations, timeout
                )
            )
        return self.retryable_creation_receipt

    async def status(self):
        print('***********************status entered')
        creation_receipt = await self.get_retryable_creation_receipt()
        if not creation_receipt:
            print('a-NOT_YET_CREATED')
            return L1ToL2MessageStatus.NOT_YET_CREATED
            
        if creation_receipt.status == 0:
            print('b-CREATION_FAILED')
            return L1ToL2MessageStatus.CREATION_FAILED
        l2_tx_receipt = await get_transaction_receipt( self.l2_provider,
            self.l2_tx_hash
        )
        if l2_tx_receipt and l2_tx_receipt.status == 1:
            print('c-REDEEMED')
            return L1ToL2MessageStatus.REDEEMED
        print('***********************status exited')
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
        print('***********************reedeem entered')
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            print("a-funds deposited on l2")
            # Load the ArbRetryableTx contract
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_signer.provider, is_classic=False
            )

            # Send the redeem transaction
            redeem_tx = arb_retryable_tx.functions.redeem(
                self.retryable_creation_id
            ).build_transaction({
                "from": self.l2_signer.account.address,
                'gasPrice': self.l2_signer.provider.eth.gas_price,
                'nonce': self.l2_signer.provider.eth.get_transaction_count(self.l2_signer.account.address),
                'chainId': self.l2_signer.provider.eth.chain_id
            })

            redeem_tx['gas'] = self.l2_signer.provider.eth.estimate_gas(redeem_tx) if overrides.get('gasLimit', None) is None else overrides['gasLimit']

            signed_txn = self.l2_signer.account.sign_transaction(redeem_tx)
            print("signed", signed_txn)
            tx_hash = self.l2_signer.provider.eth.send_raw_transaction(signed_txn.rawTransaction)
            # Wait for the transaction to be mined
            tx_receipt = self.l2_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
            print('mytex', tx_receipt)

            # Apply monkey patch to the transaction receipt
            monkey_patched_receipt = L2TransactionReceipt.monkey_patch_wait(tx_receipt)

            # Convert the monkey patched receipt to a redeem transaction
            redeem_transaction = L2TransactionReceipt.to_redeem_transaction(
                monkey_patched_receipt, self.l2_provider
            )
            print('***********************reedem exited')

            return redeem_transaction
        else:
            raise ArbSdkError(
                f"Cannot redeem as retryable does not exist. Message status: {L1ToL2MessageStatus[status]} must be: {L1ToL2MessageStatus[L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2]}."
            )

    async def cancel(self, overrides=None):
        print('***********************cancel entered')
        status = await self.status()
        if status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
            print("a-funds deposited on l2")
            # Load the ArbRetryableTx contract
            arb_retryable_tx = load_contract(
                contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_signer.provider, is_classic=False
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
                contract_name="ArbRetryableTx", address=ARB_RETRYABLE_TX_ADDRESS, provider=self.l2_signer.provider, is_classic=False
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

    # @staticmethod
    # def calculate_deposit_tx_id(
    #     l2_chain_id, message_number, from_address, to_address, value
    # ):
    #     chain_id = Web3.to_bytes(l2_chain_id).rjust(32, b"\0")
    #     msg_num = Web3.to_bytes(message_number).rjust(32, b"\0")
    #     from_addr = Web3.to_bytes(hexstr=Web3.to_checksum_address(from_address))
    #     to_addr = Web3.to_bytes(hexstr=Web3.to_checksum_address(to_address))
    #     value_bytes = Web3.to_bytes(value).rjust(32, b"\0")

    #     fields = [chain_id, msg_num, from_addr, to_addr, value_bytes]

    #     rlp_encoded = Web3.encode_rlp(fields)
    #     rlp_encoded_with_type = b"\x64" + rlp_encoded

    #     return encode_hex(keccak(rlp_encoded_with_type))


    @staticmethod
    def calculate_deposit_tx_id(
        l2_chain_id, message_number, from_address, to_address, value
    ):
        chain_id = l2_chain_id
        msg_num = message_number

        print('chain_id', chain_id)
        print('msg_num', msg_num)
        print('from_address', from_address)
        print('to_address', to_address)
        print('value', value)

        fields = [
            format_number(chain_id),
            zero_pad(format_number(msg_num), 32),
            bytes.fromhex(get_address(from_address)[2:]),
            bytes.fromhex(get_address(to_address)[2:]),
            format_number(value),
        ]

        print(fields)
        rlp_encoded = rlp.encode(fields)
        rlp_enc_with_type = b'\x64' + rlp_encoded

        retryable_tx_id = Web3.keccak(rlp_enc_with_type)
        # retryable_tx_id2 = Web3.keccak(rlp_encoded)
        # print(retryable_tx_id2.hex())

        return retryable_tx_id.hex()



    @staticmethod
    def from_event_components(
        l2_provider, message_number, sender_addr, inbox_message_event_data
    ):
        chain_id = l2_provider.eth.chain_id
        parsed_data = EthDepositMessage.parse_eth_deposit_data(inbox_message_event_data)
        print("parsed_data", parsed_data)
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
        # print(Web3.to_hex(event_data))
        if isinstance(event_data, bytes):
            event_data = Web3.to_hex(event_data)
        
        address_end = 2 + 20 * 2
        to_address = get_address("0x" + event_data[2:address_end])
        value_hex = event_data[address_end:]
        if value_hex.startswith("0"):
            # remove all the leading zeros
            value_hex = value_hex.lstrip("0")

        value = int("0x" + value_hex, 16)
        return {"to": to_address, "value": value}

    async def status(self):
        receipt = await get_transaction_receipt( self.l2_provider,
            self.l2_deposit_tx_hash
        )
        if receipt is None:
            return "PENDING"
        else:
            return "DEPOSITED"

    # async def wait(self, confirmations=None, timeout=None):
    #     # Get the L2 network information
    #     l2_network = get_l2_network(self.l2_chain_id)

    #     # Set the chosen timeout based on the provided timeout or the network's default deposit timeout
    #     chosen_timeout = (
    #         timeout if timeout is not None else l2_network["depositTimeout"]
    #     )

    #     # Start time for timeout calculation
    #     start_time = asyncio.get_event_loop().time()

    #     # Loop until the transaction is confirmed or the timeout is reached
    #     while True:
    #         print('loop1')
    #         if self.l2_deposit_tx_receipt is None:
    #             try:
    #                 print("hash", self.l2_deposit_tx_hash)
    #                 # Attempt to get the transaction receipt
    #                 self.l2_deposit_tx_receipt = (
    #                     await get_transaction_receipt( self.l2_provider,
    #                         self.l2_deposit_tx_hash
    #                     )
    #                 )
    #                 print('self.l2_deposit_tx_receipt', self.l2_deposit_tx_receipt)

    #                 # Check if the number of confirmations is met
    #                 current_block = self.l2_provider.eth.block_number
    #                 if (
    #                     confirmations is None
    #                     or current_block - self.l2_deposit_tx_receipt.blockNumber
    #                     >= confirmations
    #                 ):
    #                     return self.l2_deposit_tx_receipt

    #             except TransactionNotFound:
    #                 # If the transaction is not found, continue the loop
    #                 pass

    #             # Check if the timeout is reached
    #             if asyncio.get_event_loop().time() - start_time > chosen_timeout:
    #                 raise TimeoutError(
    #                     f"Timeout reached waiting for transaction receipt: {self.l2_deposit_tx_hash}"
    #                 )

    #             # Wait a short time before trying again
    #             await asyncio.sleep(5)

    
    async def wait(self, confirmations=None, timeout=None):
        # THIS FUNCTION IS REWRITTEN FROM ABOVE

        # Get the L2 network information
        l2_network = get_l2_network(self.l2_chain_id)

        # Set the chosen timeout based on the provided timeout or the network's default deposit timeout
        chosen_timeout = (
            timeout if timeout is not None else l2_network["depositTimeout"]
        )

        if (self.l2_deposit_tx_receipt is None):
            self.l2_deposit_tx_receipt = (
                await get_transaction_receipt( self.l2_provider,
                    self.l2_deposit_tx_hash,
                    confirmations,
                    chosen_timeout
                )
            )
            print('self.l2_deposit_tx_receipt', self.l2_deposit_tx_receipt)

        return self.l2_deposit_tx_receipt