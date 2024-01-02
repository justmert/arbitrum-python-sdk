import asyncio
from web3 import Web3
from web3.exceptions import TimeExhausted
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import l2_networks
from src.lib.data_entities.constants import ARB_SYS_ADDRESS
from .arb_provider import ArbitrumProvider
import json


# Create a contract instance
def get_contract_instance(web3_provider: Web3, contract_address: str, contract_abi: dict):
    return web3_provider.eth.contract(address=contract_address, abi=contract_abi)

# Get the base fee
async def get_base_fee(provider: Web3):
    latest_block = provider.eth.getBlock('latest')
    base_fee = latest_block['baseFeePerGas']
    if not base_fee:
        raise ArbSdkError('Latest block did not contain base fee, ensure provider is connected to a network that supports EIP 1559.')
    return base_fee

# Wait for a certain amount of time
async def wait(ms: int):
    await asyncio.sleep(ms/1000)

# Get transaction receipt
async def get_transaction_receipt(web3_instance, tx_hash, confirmations=None, timeout=None):
    try:
        receipt = await web3_instance.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return receipt if receipt['blockNumber'] >= confirmations else None
    except TimeExhausted:
        return None
    except Exception as e:
        raise e

def is_defined(val):
    return val is not None


async def is_arbitrum_chain(web3_instance):
    try:
        # Assuming you have the ABI for ArbSys in a JSON file
        with open('src/abi/ArbSys.json') as f:
            ARBSYS_ABI = json.load(f)
        arb_sys_contract = web3_instance.eth.contract(address=Web3.to_checksum_address(ARB_SYS_ADDRESS), abi=ARBSYS_ABI)
        await arb_sys_contract.functions.arbOSVersion().call()
        return True
    except Exception:
        return False


async def get_first_block_for_l1_block(provider, for_l1_block, allow_greater=False, min_l2_block=None, max_l2_block='latest'):
    if not await is_arbitrum_chain(provider):
        return for_l1_block

    arb_provider = ArbitrumProvider(provider)
    current_arb_block = await arb_provider.get_block_number()
    arbitrum_chain_id = (await arb_provider.get_network()).chainId
    nitro_genesis_block = l2_networks[arbitrum_chain_id]["nitroGenesisBlock"]

    async def get_l1_block(for_l2_block):
        block = await arb_provider.get_block(for_l2_block)
        return block["l1BlockNumber"]

    if not min_l2_block:
        min_l2_block = nitro_genesis_block

    if max_l2_block == 'latest':
        max_l2_block = current_arb_block

    if min_l2_block >= max_l2_block:
        raise ValueError(f"'minL2Block' ({min_l2_block}) must be lower than 'maxL2Block' ({max_l2_block}).")

    if min_l2_block < nitro_genesis_block:
        raise ValueError(f"'minL2Block' ({min_l2_block}) cannot be below 'nitroGenesisBlock', which is {nitro_genesis_block} for the current network.")

    start = min_l2_block
    end = max_l2_block

    result_for_target_block = None
    result_for_greater_block = None

    while start <= end:
        mid = start + (end - start) // 2
        l1_block = await get_l1_block(mid)

        if l1_block == for_l1_block:
            result_for_target_block = mid
            end = mid - 1
        elif l1_block < for_l1_block:
            start = mid + 1
        else:
            if allow_greater:
                result_for_greater_block = mid
            end = mid - 1

    return result_for_target_block if result_for_target_block is not None else result_for_greater_block



async def get_block_ranges_for_l1_block(provider, for_l1_block, allow_greater=False, min_l2_block=None, max_l2_block='latest'):
    arb_provider = ArbitrumProvider(provider)
    current_l2_block = await arb_provider.get_block_number()

    if not max_l2_block or max_l2_block == 'latest':
        max_l2_block = current_l2_block

    start_block = await get_first_block_for_l1_block(
        provider, for_l1_block, allow_greater=False, min_l2_block=min_l2_block, max_l2_block=max_l2_block
    )

    end_block = await get_first_block_for_l1_block(
        provider, for_l1_block + 1, allow_greater=True, min_l2_block=min_l2_block, max_l2_block=max_l2_block
    )

    if not start_block:
        return [None, None]

    if start_block and end_block:
        return [start_block, end_block - 1]

    return [start_block, max_l2_block]
