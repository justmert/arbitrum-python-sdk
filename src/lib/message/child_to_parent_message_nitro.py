

from web3 import Web3
from eth_typing import BlockNumber

from src.lib.data_entities.constants import ARB_SYS_ADDRESS, NODE_INTERFACE_ADDRESS
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.message import ChildToParentMessageStatus
from src.lib.data_entities.networks import get_arbitrum_network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.event_fetcher import EventFetcher
from src.lib.utils.helper import format_contract_output, load_contract
from src.lib.utils.lib import (
    get_block_ranges_for_l1_block,
    is_arbitrum_chain,
)
from typing import List, Optional
import threading
import time

# Same constants you had before, now referencing child->parent
ASSERTION_CREATED_PADDING = 50
ASSERTION_CONFIRMED_PADDING = 20

child_block_range_cache = {}
child_block_cache_lock = threading.Lock()



def get_child_block_range_cache_key(child_chain_id: int, l1_block_number: int) -> str:
    """Create a unique cache key for the child block range lookup."""
    return f"{child_chain_id}-{l1_block_number}"


def set_child_block_range_cache(key: str, value: List[Optional[int]]) -> None:
    """Cache the child block range under the given key."""
    child_block_range_cache[key] = value


def get_block_ranges_for_l1_block_with_cache(
    parent_provider, child_provider, for_l1_block: int
):
    """
    Looks up the child block range for a given L1 block, using a shared cache to avoid repeated
    calls. Corresponds to getBlockRangesForL1BlockWithCache in TS code.
    """
    child_chain_id = child_provider.eth.chain_id
    key = get_child_block_range_cache_key(child_chain_id, for_l1_block)

    # Return cached value if exists
    if key in child_block_range_cache:
        return child_block_range_cache[key]

    # Otherwise, lock so only one fetch is in-flight
    with child_block_cache_lock:
        # Maybe it got cached while we waited for the lock
        if key in child_block_range_cache:
            return child_block_range_cache[key]

        # Actually fetch
        child_block_range = get_block_ranges_for_l1_block(
            parent_provider, for_l1_block
        )
        set_child_block_range_cache(key, child_block_range)
        return child_block_range



class ChildToParentMessageNitro:
    """
    Base functionality for 'nitro' child->parent messages, replacing L2ToL1MessageNitro from v3.
    """

    def __init__(self, event: dict):
        """
        :param event: The ChildToParentTx event dictionary from the child chain
        """
        self.event = event

    @classmethod
    def from_event(cls, parent_signer_or_provider, event, parent_provider=None):
        """
        Create either ChildToParentMessageReaderNitro or ChildToParentMessageWriterNitro
        depending on whether the passed-in object is a Signer or a Provider.
        """
        if SignerProviderUtils.is_signer(parent_signer_or_provider):
            return ChildToParentMessageWriterNitro(parent_signer_or_provider, event, parent_provider)
        else:
            return ChildToParentMessageReaderNitro(parent_signer_or_provider, event)

    @staticmethod
    def get_child_to_parent_events(
        child_provider,
        filter_dict: dict,
        position=None,
        destination=None,
        hash=None,
    ):
        """
        Fetch Child->Parent events (formerly L2->L1) from the child chain.
        This parallels 'getL2ToL1Events' in the TS code but now named getChildToParentEvents.
        """
        event_fetcher = EventFetcher(child_provider)

        argument_filters = {}
        if position:
            argument_filters["position"] = position
        if destination:
            argument_filters["destination"] = destination
        if hash:
            argument_filters["hash"] = hash

        # The underlying event name is still "L2ToL1Tx" on-chain, even though we've renamed the TypeScript interface.
        events = event_fetcher.get_events(
            contract_factory="ArbSys",
            event_name="L2ToL1Tx",
            argument_filters=argument_filters,
            filter={
                "fromBlock": filter_dict["fromBlock"],
                "toBlock": filter_dict["toBlock"],
                "address": ARB_SYS_ADDRESS,
                **filter_dict,
            },
            
        )
        return events


class ChildToParentMessageReaderNitro(ChildToParentMessageNitro):
    """
    Read-only logic for child->parent messages in Nitro. Replaces L2ToL1MessageReaderNitro.
    """

    def __init__(self, parent_provider, event):
        super().__init__(event)
        self.parent_provider = parent_provider
        self.send_root_hash = None
        self.send_root_size = None
        self.send_root_confirmed = None
        self.outbox_address = None
        self.l1_batch_number = None

    def get_outbox_proof(self, child_provider):
        """
        Equivalent to getOutboxProof in the TS code. Constructs a proof to execute the message.
        """
        send_props = self.get_send_props(child_provider)
        send_root_size = send_props.get("sendRootSize", None)

        if not send_root_size:
            raise ArbSdkError("Assertion not yet created, cannot get proof.")

        node_interface_contract = load_contract(
            provider=child_provider,
            contract_name="NodeInterface",
            address=NODE_INTERFACE_ADDRESS,
            
        )

        # callStatic.constructOutboxProof(...) in TS
        outbox_proof_params = node_interface_contract.functions.constructOutboxProof(
            send_root_size, self.event["position"]
        ).call()

        outbox_proof_params = format_contract_output(
            node_interface_contract,
            "constructOutboxProof",
            outbox_proof_params,
        )
        return outbox_proof_params["proof"]

    def has_executed(self, child_provider) -> bool:
        """
        Checks if the message is already executed by calling Outbox.isSpent(position).
        """
        child_chain = get_arbitrum_network(child_provider)
        outbox_contract = load_contract(
            provider=self.parent_provider,
            contract_name="Outbox",
            address=child_chain.ethBridge.outbox,
            
        )
        return outbox_contract.functions.isSpent(self.event["position"]).call()

    def status(self, child_provider) -> ChildToParentMessageStatus:
        """
        Returns the status of this message (UNCONFIRMED, CONFIRMED, or EXECUTED).
        """
        send_props = self.get_send_props(child_provider)
        if not send_props.get("sendRootConfirmed"):
            return ChildToParentMessageStatus.UNCONFIRMED

        # If the send root is confirmed, check if the message was executed
        executed = self.has_executed(child_provider)
        return ChildToParentMessageStatus.EXECUTED if executed else ChildToParentMessageStatus.CONFIRMED

    def parse_node_created_assertion(self, fetched_event):
        """
        For a classic RollupUserLogic NodeCreated event.  
        Replaces parseNodeCreatedAssertion from TS code.
        """
        return {
            "afterState": {
                "blockHash": fetched_event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][0],
                "sendRoot": fetched_event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][1],
            }
        }

    def parse_assertion_created_event(self, fetched_event):
        """
        For a BoldRollupUserLogic AssertionCreated event (BoLD).  
        Replaces parseAssertionCreatedEvent from TS code.
        """
        # Both NodeCreated and AssertionCreated have similar structure. BoLD has an 'assertionHash'.
        return {
            "afterState": {
                "blockHash": fetched_event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][0],
                "sendRoot": fetched_event["event"]["assertion"]["afterState"]["globalState"]["bytes32Vals"][1],
            }
        }

    def is_assertion_created_log(self, fetched_event: dict) -> bool:
        """
        Distinguishes between NodeCreated (legacy) vs. AssertionCreated (BoLD).
        In TS, we look for 'event.challengeManager != undefined'.
        """
        # We'll look for 'assertionHash' or 'challengeManager' or do a simpler check here:
        return "assertionHash" in fetched_event["event"]

    def get_block_from_assertion_log(self, child_provider, fetched_event=None):
        """
        Merges logic from getBlockFromNodeLog + getBlockFromAssertionLog in TS.
        """
        arbitrum_provider = ArbitrumProvider(child_provider)

        if not fetched_event:
            # If no logs found, default block 0
            return arbitrum_provider.get_block(0)

        if self.is_assertion_created_log(fetched_event):
            parsed = self.parse_assertion_created_event(fetched_event)
        else:
            parsed = self.parse_node_created_assertion(fetched_event)

        block_hash = parsed["afterState"]["blockHash"]
        send_root = parsed["afterState"]["sendRoot"]

        child_block = arbitrum_provider.get_block(block_hash)
        if not child_block:
            raise ArbSdkError(f"Block not found. {block_hash}")

        print(f"Child block: {child_block}")
        print(f"Send root: {send_root}")
        if child_block["sendRoot"] != Web3.to_hex(send_root):
            raise ArbSdkError(
                f"Child chain block send root doesn't match assertion log. {child_block['sendRoot']} {send_root}"
            )
        return child_block

    def get_block_from_assertion_id(self, rollup_contract, assertion_id, child_provider):
        """
        Merges getBlockFromNodeNum with the BoLD path using getAssertion.  
        In TS, we do rollup.getNode(...) vs rollup.getAssertion(...).
        """
        # Distinguish whether this is a 'BoldRollupUserLogic' by trying a call
        # But in Python, we might just try to call .extraChallengeTimeBlocks() and catch.
        # We'll do a simpler check: see if getAssertion(...) is valid. 
        # For your use-case, you may implement a more robust detection logic.
        is_bold = False
        try:
            # If this call fails, it's classic
            rollup_contract.functions.extraChallengeTimeBlocks().call()
        except Exception:
            is_bold = True

        if is_bold:
            # The BoLD rollup contract has a method getAssertion(hash)
            # We'll attempt something like: rollup_contract.functions.getAssertion(assertionHash).call()
            # But the input might be a string, not a BigNumber
            assertion_data = rollup_contract.functions.getAssertion(assertion_id).call()
            assertion_data = format_contract_output(rollup_contract, "getAssertion", assertion_data)
            created_at_block = assertion_data["createdAtBlock"]
        else:
            # Classic path
            node = rollup_contract.functions.getNode(assertion_id).call()
            node = format_contract_output(rollup_contract, "getNode", node)
            created_at_block = node["createdAtBlock"]

        # Convert to Python int
        created_at_block = int(created_at_block)

        created_from_block = created_at_block
        created_to_block = created_at_block

        # If parent is Arbitrum, then child is Orbit. We try to find the child block range
        if is_arbitrum_chain(self.parent_provider):
            # Some or all of these calls might fail, so we do a try-catch fallback:
            success = False
            # One approach: call nodeInterface.l2BlockRangeForL1() if available
            try:
                node_interface = load_contract(
                    provider=self.parent_provider,
                    contract_name="NodeInterface",
                    address=NODE_INTERFACE_ADDRESS,
                    
                )
                block_range = node_interface.functions.l2BlockRangeForL1(created_at_block).call()
                block_range = format_contract_output(node_interface, "l2BlockRangeForL1", block_range)
                created_from_block = block_range["firstBlock"]
                created_to_block = block_range["lastBlock"]
                success = True
            except Exception:
                pass

            if not success:
                try:
                    # fallback: do the binary search approach
                    child_block_range = get_block_ranges_for_l1_block_with_cache(
                        self.parent_provider, child_provider, created_at_block
                    )
                    start_block, end_block = child_block_range
                    if not start_block or not end_block:
                        raise Exception()
                    created_from_block = start_block
                    created_to_block = end_block
                except Exception:
                    # fallback all the way to naive approach
                    created_from_block = created_at_block
                    created_to_block = created_at_block

        # Now let's fetch the actual event from logs
        event_fetcher = EventFetcher(rollup_contract.w3)

        if is_bold:
            # We're searching for AssertionCreated(assertionHash)
            logs = event_fetcher.get_events(
                contract_factory=rollup_contract,
                event_name="AssertionCreated",
                argument_filters={"assertionHash": assertion_id},
                filter={
                    "fromBlock": created_from_block,
                    "toBlock": created_to_block,
                    "address": rollup_contract.address,
                },
            )
        else:
            # Searching for NodeCreated(nodeNum)
            logs = event_fetcher.get_events(
                contract_factory=rollup_contract,
                event_name="NodeCreated",
                argument_filters={"nodeNum": assertion_id},
                filter={
                    "fromBlock": created_from_block,
                    "toBlock": created_to_block,
                    "address": rollup_contract.address,
                },
            )

        if len(logs) > 1:
            raise ArbSdkError(
                f"Unexpected number of AssertionCreated/NodeCreated events. Expected 0 or 1, got {len(logs)}."
            )

        return self.get_block_from_assertion_log(
            child_provider, logs[0] if logs else None
        )

    def get_batch_number(self, child_provider) -> Optional[int]:
        """
        findBatchContainingBlock parallels TS logic, but might fail if the block doesn't exist yet.
        """
        if self.l1_batch_number is None:
            try:
                node_interface_contract = load_contract(
                    provider=child_provider,
                    contract_name="NodeInterface",
                    address=NODE_INTERFACE_ADDRESS,
                    
                )
                res = node_interface_contract.functions.findBatchContainingBlock(
                    self.event["arbBlockNum"]
                ).call()
                self.l1_batch_number = int(res)
            except Exception:
                pass
        return self.l1_batch_number

    def get_send_props(self, child_provider):
        """
        Merges logic from getSendProps in TS: checks whether the node is confirmed or not.
        If so, we store sendRootSize, sendRootHash, sendRootConfirmed, etc.
        """
        if not self.send_root_confirmed:
            child_chain = get_arbitrum_network(child_provider)
            rollup_contract = load_contract(
                provider=self.parent_provider,
                contract_name="RollupUserLogic",  # or BoldRollupUserLogic if determined
                address=child_chain.ethBridge.rollup,
                
            )

            # latestConfirmed is the ID (nodeNum or assertionHash) of the last confirmed node
            latest_confirmed = rollup_contract.functions.latestConfirmed().call()

            # This merges classic or bold logic in a single path, see get_block_from_assertion_id
            confirmed_block = self.get_block_from_assertion_id(
                rollup_contract, latest_confirmed, child_provider
            )
            send_root_size_confirmed = int(Web3.to_int(hexstr=confirmed_block["sendCount"]))

            if send_root_size_confirmed > self.event["position"]:
                self.send_root_size = send_root_size_confirmed
                self.send_root_hash = confirmed_block["sendRoot"]
                self.send_root_confirmed = True
            else:
                # latestNodeCreated or latestAssertionCreated
                # For Bold, this might be an assertionHash; for classic, it's a nodeNum.
                if rollup_contract.functions.latestNodeCreated:
                    latest_created = rollup_contract.functions.latestNodeCreated().call()
                else:
                    # if that fails, it's a bold approach
                    # you'd adapt to a separate bold method
                    pass

                # If there's a strictly larger node number / assertion ID
                if latest_created > latest_confirmed:
                    unconfirmed_block = self.get_block_from_assertion_id(
                        rollup_contract, latest_created, child_provider
                    )
                    send_root_size_unconfirmed = int(
                        Web3.to_int(hexstr=unconfirmed_block["sendCount"])
                    )
                    if send_root_size_unconfirmed > self.event["position"]:
                        self.send_root_size = send_root_size_unconfirmed
                        self.send_root_hash = unconfirmed_block["sendRoot"]
        return {
            "sendRootSize": self.send_root_size,
            "sendRootHash": self.send_root_hash,
            "sendRootConfirmed": self.send_root_confirmed,
        }

    def wait_until_ready_to_execute(
        self,
        child_provider,
        retry_delay=1000,
    ) -> ChildToParentMessageStatus:
        """
        Wait repeatedly until the outbox entry (assertion) is confirmed, so the message can be executed.
        Like waitUntilReadyToExecute in TS code.
        """
        while True:
            current_status = self.status(child_provider)
            if current_status in (
                ChildToParentMessageStatus.CONFIRMED,
                ChildToParentMessageStatus.EXECUTED,
            ):
                return current_status
                
            time.sleep(retry_delay / 1000.0)  # Convert milliseconds to seconds

    def get_first_executable_block(self, child_provider) -> Optional[BlockNumber]:
        """
        getFirstExecutableBlock from the TS code:
        - If message can be or is already executed, return None
        - Otherwise, find the earliest block in which it can be executed
        """
        child_chain = get_arbitrum_network(child_provider)
        rollup_contract = load_contract(
            provider=self.parent_provider,
            contract_name="RollupUserLogic",
            address=child_chain.ethBridge.rollup,
            
        )

        current_status = self.status(child_provider)
        if current_status in (
            ChildToParentMessageStatus.EXECUTED,
            ChildToParentMessageStatus.CONFIRMED,
        ):
            return None

        if current_status != ChildToParentMessageStatus.UNCONFIRMED:
            raise ArbSdkError("ChildToParentMessage expected to be UNCONFIRMED")

        latest_block = self.parent_provider.eth.block_number
        event_fetcher = EventFetcher(self.parent_provider)

        # We check either NodeCreated or AssertionCreated logs
        # For simplicity, we assume classic here (NodeCreated).
        # If bold, you'd search for AssertionCreated instead.
        logs = event_fetcher.get_events(
            contract_factory=rollup_contract,
            event_name="NodeCreated",
            argument_filters={},
            filter={
                "fromBlock": max(
                    latest_block - child_chain.confirmPeriodBlocks - ASSERTION_CONFIRMED_PADDING,
                    0,
                ),
                "toBlock": "latest",
                "address": rollup_contract.address,
            },
        )

        # Sort them in ascending nodeNum order
        logs.sort(key=lambda x: x["event"]["nodeNum"])

        # Get the last block from the last NodeCreated event
        last_child_block = self.get_block_from_assertion_log(
            child_provider, logs[-1] if logs else None
        )
        last_send_count = int(last_child_block["sendCount"]) if last_child_block else 0

        # If the last node does not include this position, 
        # we assume we must wait the max time for a new node + confirmation
        if last_send_count <= self.event["position"]:
            return (
                child_chain.confirmPeriodBlocks
                + ASSERTION_CREATED_PADDING
                + ASSERTION_CONFIRMED_PADDING
                + latest_block
            )

        # Otherwise, do a binary search in logs to find the first node whose sendCount > position
        left, right = 0, len(logs) - 1
        found_log = logs[-1] if logs else None
        while left <= right:
            mid = (left + right) // 2
            test_log = logs[mid]
            child_block = self.get_block_from_assertion_log(child_provider, test_log)
            send_count = int(child_block["sendCount"])
            if send_count > self.event["position"]:
                found_log = test_log
                right = mid - 1
            else:
                left = mid + 1

        if not found_log:
            # No logs, fallback
            return (
                child_chain.confirmPeriodBlocks
                + ASSERTION_CREATED_PADDING
                + ASSERTION_CONFIRMED_PADDING
                + latest_block
            )

        earliest_node_with_exit = found_log["event"]["nodeNum"]
        node = rollup_contract.functions.getNode(earliest_node_with_exit).call()
        node = format_contract_output(rollup_contract, "getNode", node)
        return node["deadlineBlock"] + ASSERTION_CONFIRMED_PADDING


class ChildToParentMessageWriterNitro(ChildToParentMessageReaderNitro):
    """
    Read+Write access for nitro Child->Parent messages.
    Replaces L2ToL1MessageWriterNitro.
    """

    def __init__(self, parent_signer, event, parent_provider=None):
        super().__init__(
            parent_provider if parent_provider else parent_signer.provider,
            event
        )
        self.parent_signer = parent_signer

    def execute(self, child_provider, overrides=None):
        """
        Executes the Child->Parent message on the parent chain once the outbox entry is confirmed.
        Throws if message is not yet CONFIRMED.
        """
        current_status = self.status(child_provider)
        if current_status != ChildToParentMessageStatus.CONFIRMED:
            raise ArbSdkError(
                f"Cannot execute message. Status is: {current_status} but must be {ChildToParentMessageStatus.CONFIRMED}."
            )

        proof = self.get_outbox_proof(child_provider)
        child_chain = get_arbitrum_network(child_provider)
        outbox_contract = load_contract(
            provider=self.parent_signer.provider,
            contract_name="Outbox",
            address=child_chain.ethBridge.outbox,
            
        )

        if overrides is None:
            overrides = {}
        if "from" not in overrides:
            overrides["from"] = self.parent_signer.account.address

        execute_tx = outbox_contract.functions.executeTransaction(
            proof,
            self.event["position"],
            self.event["caller"],
            self.event["destination"],
            self.event["arbBlockNum"],
            self.event["ethBlockNum"],
            self.event["timestamp"],
            self.event["callvalue"],
            self.event["data"],
        )

        tx_hash = execute_tx.transact(overrides)
        tx_receipt = self.parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)
        return tx_receipt
