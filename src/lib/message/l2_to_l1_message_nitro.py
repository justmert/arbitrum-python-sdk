import asyncio

from web3 import Web3

from src.lib.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.message import L2ToL1MessageStatus
from src.lib.data_entities.networks import get_l2_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import (
    format_contract_output,
    load_contract,
)
from src.lib.utils.lib import get_block_ranges_for_l1_block, is_arbitrum_chain

ASSERTION_CREATED_PADDING = 50
ASSERTION_CONFIRMED_PADDING = 20

l2_block_range_cache = {}
lock = asyncio.Lock()


def get_l2_block_range_cache_key(l2_chain_id, l1_block_number):
    return f"{l2_chain_id}-{l1_block_number}"


def set_l2_block_range_cache(key, value):
    l2_block_range_cache[key] = value


async def get_block_ranges_for_l1_block_with_cache(l1_provider, l2_provider, for_l1_block):
    l2_chain_id = l2_provider.eth.chainId
    key = get_l2_block_range_cache_key(l2_chain_id, for_l1_block)

    if key in l2_block_range_cache:
        return l2_block_range_cache[key]

    async with lock:
        if key in l2_block_range_cache:
            return l2_block_range_cache[key]

        l2_block_range = await get_block_ranges_for_l1_block(l1_provider, for_l1_block)
        set_l2_block_range_cache(key, l2_block_range)

        return l2_block_range_cache[key]


class L2ToL1MessageNitro:
    def __init__(self, event):
        self.event = event

    @classmethod
    async def from_event(cls, l1_signer_or_provider, event, l1_provider=None):
        if SignerProviderUtils.is_signer(l1_signer_or_provider):
            return L2ToL1MessageWriterNitro(l1_signer_or_provider, event, l1_provider)
        else:
            return L2ToL1MessageReaderNitro(l1_signer_or_provider, event)

    @staticmethod
    async def get_l2_to_l1_events(l2_provider, filter, position=None, destination=None, hash=None):
        event_fetcher = EventFetcher(l2_provider)

        argument_filters = {}
        if position:
            argument_filters["position"] = position
        if destination:
            argument_filters["destination"] = destination
        if hash:
            argument_filters["hash"] = hash

        events = await event_fetcher.get_events(
            contract_factory="ArbSys",
            event_name="L2ToL1Tx",
            argument_filters=argument_filters,
            filter={
                "fromBlock": filter["fromBlock"],
                "toBlock": filter["toBlock"],
                "address": ARB_SYS_ADDRESS,
                **filter,
            },
            is_classic=False,
        )
        return events


class L2ToL1MessageReaderNitro(L2ToL1MessageNitro):
    def __init__(self, l1_provider, event):
        super().__init__(event)
        self.l1_provider = l1_provider
        self.send_root_hash = None
        self.send_root_size = None
        self.send_root_confirmed = None
        self.outbox_address = None
        self.l1_batch_number = None

    async def get_outbox_proof(self, l2_provider):
        send_props = await self.get_send_props(l2_provider)
        send_root_size = send_props.get("sendRootSize", None)

        if not send_root_size:
            raise Exception("Node not yet created, cannot get proof.")

        node_interface_contract = load_contract(
            provider=l2_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            is_classic=False,
        )

        outbox_proof_params = node_interface_contract.functions.constructOutboxProof(
            send_root_size, self.event["position"]
        ).call()
        outbox_proof_params = format_contract_output(
            node_interface_contract, "constructOutboxProof", outbox_proof_params
        )
        return outbox_proof_params["proof"]

    async def has_executed(self, l2_provider):
        l2_network = get_l2_network(l2_provider)

        outbox_contract = load_contract(
            provider=self.l1_provider,
            contract_name="Outbox",
            address=l2_network.ethBridge.outbox,
            is_classic=False,
        )
        return outbox_contract.functions.isSpent(self.event["position"]).call()

    async def status(self, l2_provider):
        send_props = await self.get_send_props(l2_provider)

        send_root_confirmed = send_props.get("sendRootConfirmed", None)

        if not send_root_confirmed:
            return L2ToL1MessageStatus.UNCONFIRMED

        return L2ToL1MessageStatus.EXECUTED if await self.has_executed(l2_provider) else L2ToL1MessageStatus.CONFIRMED

    def parse_node_created_assertion(self, event):
        return {
            "afterState": {
                "blockHash": event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][0],
                "sendRoot": event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][1],
            },
        }

    async def get_block_from_node_log(self, l2_provider, log=None):
        arbitrum_provider = ArbitrumProvider(l2_provider)

        if not log:
            return await arbitrum_provider.get_block(0)

        parsed_log = self.parse_node_created_assertion(log)
        l2_block = await arbitrum_provider.get_block(parsed_log["afterState"]["blockHash"])
        if not l2_block:
            raise Exception(f"Block not found. {parsed_log['afterState']['blockHash']}")

        if l2_block["sendRoot"] != Web3.to_hex(parsed_log["afterState"]["sendRoot"]):
            raise Exception(
                f"L2 block send root doesn't match parsed log. {l2_block['sendRoot']} {parsed_log['afterState']['sendRoot']}"
            )
        return l2_block

    async def get_block_from_node_num(self, rollup, node_num, l2_provider):
        node = rollup.functions.getNode(node_num).call()
        node = format_contract_output(rollup, "getNode", node)

        created_at_block = node["createdAtBlock"]

        created_from_block = created_at_block
        created_to_block = created_at_block

        if await is_arbitrum_chain(self.l1_provider):
            try:
                l2_block_range = await get_block_ranges_for_l1_block_with_cache(
                    self.l1_provider, l2_provider, created_at_block
                )
                start_block, end_block = l2_block_range
                if not start_block or not end_block:
                    raise Exception()
                created_from_block = start_block
                created_to_block = end_block
            except Exception:
                created_from_block = created_at_block
                created_to_block = created_at_block

        event_fetcher = EventFetcher(rollup.w3)

        argument_filters = {"nodeNum": node_num}

        logs = await event_fetcher.get_events(
            contract_factory=rollup,
            event_name="NodeCreated",
            argument_filters=argument_filters,
            filter={
                "fromBlock": created_from_block,
                "toBlock": created_to_block,
                "address": rollup.address,
            },
        )

        if len(logs) > 1:
            raise Exception(f"Unexpected number of NodeCreated events. Expected 0 or 1, got {len(logs)}.")

        return await self.get_block_from_node_log(l2_provider, logs[0] if logs else None)

    async def get_batch_number(self, l2_provider):
        if self.l1_batch_number is None:
            try:
                node_interface_contract = load_contract(
                    provider=l2_provider,
                    contract_name="NodeInterface",
                    address=NODE_INTERFACE_ADDRESS,
                    is_classic=False,
                )
                res = node_interface_contract.functions.findBatchContainingBlock(self.event["arbBlockNum"]).call()
                self.l1_batch_number = int(res)

            except Exception:
                pass
        return self.l1_batch_number

    async def get_send_props(self, l2_provider):
        if not self.send_root_confirmed:
            l2_network = get_l2_network(l2_provider)

            rollup_contract = load_contract(
                provider=self.l1_provider,
                contract_name="RollupUserLogic",
                address=l2_network.ethBridge.rollup,
                is_classic=False,
            )

            latest_confirmed_node_num = rollup_contract.functions.latestConfirmed().call()
            ("latest_confirmed_node_num", latest_confirmed_node_num)
            l2_block_confirmed = await self.get_block_from_node_num(
                rollup_contract, latest_confirmed_node_num, l2_provider
            )
            ("l2_block_confirmed", l2_block_confirmed)
            send_root_size_confirmed = Web3.to_int(hexstr=l2_block_confirmed["sendCount"])

            if send_root_size_confirmed > self.event["position"]:
                self.send_root_size = send_root_size_confirmed
                self.send_root_hash = l2_block_confirmed["sendRoot"]
                self.send_root_confirmed = True
            else:
                latest_node_num = rollup_contract.functions.latestNodeCreated().call()

                if latest_node_num > latest_confirmed_node_num:
                    l2_block = await self.get_block_from_node_num(rollup_contract, latest_node_num, l2_provider)

                    send_root_size = Web3.to_int(hexstr=l2_block["sendCount"])

                    if send_root_size > self.event["position"]:
                        self.send_root_size = send_root_size
                        self.send_root_hash = l2_block["sendRoot"]

        return {
            "sendRootSize": self.send_root_size,
            "sendRootHash": self.send_root_hash,
            "sendRootConfirmed": self.send_root_confirmed,
        }

    async def wait_until_ready_to_execute(self, l2_provider, retry_delay=1000):
        status = await self.status(l2_provider)
        if status in [L2ToL1MessageStatus.CONFIRMED, L2ToL1MessageStatus.EXECUTED]:
            return
        else:
            await asyncio.sleep(retry_delay / 1000)
            await self.wait_until_ready_to_execute(l2_provider, retry_delay)

    async def get_first_executable_block(self, l2_provider):
        l2_network = get_l2_network(l2_provider)

        rollup_contract = load_contract(
            provider=self.l1_provider,
            contract_name="RollupUserLogic",
            address=l2_network.ethBridge.rollup,
            is_classic=False,
        )

        status = await self.status(l2_provider)
        if status in [L2ToL1MessageStatus.EXECUTED, L2ToL1MessageStatus.CONFIRMED]:
            return None

        if status != L2ToL1MessageStatus.UNCONFIRMED:
            raise Exception("L2ToL1Msg expected to be unconfirmed")

        latest_block = self.l1_provider.eth.block_number
        event_fetcher = EventFetcher(self.l1_provider)

        argument_filters = {}

        logs = await event_fetcher.get_events(
            contract_factory=rollup_contract,
            event_name="NodeCreated",
            argument_filters=argument_filters,
            filter={
                "fromBlock": max(
                    latest_block - l2_network.confirm_period_blocks - ASSERTION_CONFIRMED_PADDING,
                    0,
                ),
                "toBlock": "latest",
                "address": rollup_contract.address,
            },
        )

        logs.sort(key=lambda x: x["event"]["nodeNum"])

        last_l2_block = await self.get_block_from_node_log(l2_provider, logs[-1] if logs else None)
        last_send_count = last_l2_block["sendCount"] if last_l2_block else 0

        if last_send_count <= self.event["position"]:
            return (
                l2_network.confirm_period_blocks
                + ASSERTION_CREATED_PADDING
                + ASSERTION_CONFIRMED_PADDING
                + latest_block
            )

        left, right = 0, len(logs) - 1
        found_log = logs[-1]
        while left <= right:
            mid = (left + right) // 2
            log = logs[mid]
            l2_block = await self.get_block_from_node_log(l2_provider, log)
            send_count = l2_block["sendCount"]
            if send_count > self.event["position"]:
                found_log = log
                right = mid - 1
            else:
                left = mid + 1

        earliest_node_with_exit = found_log["event"]["nodeNum"]
        node = rollup_contract.functions.getNode(earliest_node_with_exit).call()
        return node["deadlineBlock"] + ASSERTION_CONFIRMED_PADDING


class L2ToL1MessageWriterNitro(L2ToL1MessageReaderNitro):
    def __init__(self, l1_signer, event, l1_provider=None):
        super().__init__(l1_provider if l1_provider else l1_signer.provider, event)
        self.l1_signer = l1_signer

    async def execute(self, l2_provider, overrides=None):
        status = await self.status(l2_provider)
        if status != L2ToL1MessageStatus.CONFIRMED:
            raise Exception(f"Cannot execute message. Status is: {status} but must be {L2ToL1MessageStatus.CONFIRMED}.")

        proof = await self.get_outbox_proof(l2_provider)
        l2_network = get_l2_network(l2_provider)

        outbox_contract = load_contract(
            provider=self.l1_signer.provider,
            contract_name="Outbox",
            address=l2_network.ethBridge.outbox,
            is_classic=False,
        )

        if overrides is None:
            overrides = {}

        if "from" not in overrides:
            overrides["from"] = self.l1_signer.account.address

        transaction_hash = outbox_contract.functions.executeTransaction(
            proof,
            self.event["position"],
            self.event["caller"],
            self.event["destination"],
            self.event["arbBlockNum"],
            self.event["ethBlockNum"],
            self.event["timestamp"],
            self.event["callvalue"],
            self.event["data"],
        ).transact(overrides)

        tx_receipt = self.l1_signer.provider.eth.wait_for_transaction_receipt(transaction_hash)
        return tx_receipt
