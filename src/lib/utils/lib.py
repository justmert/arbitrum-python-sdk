import asyncio
from web3 import Web3
from web3.exceptions import TimeExhausted
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import l2_networks
from src.lib.data_entities.constants import ARB_SYS_ADDRESS
from .arb_provider import ArbitrumProvider
import json
from web3.exceptions import TransactionNotFound


# Create a contract instance
def get_contract_instance(web3_provider: Web3, contract_address: str, contract_abi: dict):
    return web3_provider.eth.contract(address=contract_address, abi=contract_abi)

# Get the base fee
async def get_base_fee(provider: Web3):
    latest_block = provider.eth.get_block('latest')
    base_fee = latest_block['baseFeePerGas']
    if not base_fee:
        raise ArbSdkError('Latest block did not contain base fee, ensure provider is connected to a network that supports EIP 1559.')
    return base_fee

# Wait for a certain amount of time
async def wait(ms: int):
    await asyncio.sleep(ms/1000)

# Get transaction receipt
async def get_transaction_receipt(web3_instance, tx_hash, confirmations=None, timeout=None):
    # Check if confirmations or timeout is provided
    if confirmations or timeout:
        try:
            print('buraya girdi')
            print(confirmations)
            print(timeout)
            print('tx_hash', tx_hash)
            receipt = web3_instance.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout / 1000) 
            # Additional check for confirmations if needed
            if confirmations:
                latest_block = web3_instance.eth.block_number
                if latest_block - receipt.blockNumber < confirmations:
                    return None
            return receipt
        except TimeExhausted:
            return None
        
        except Exception as e:
            print("Error waiting for transaction receipt")
            raise e
    else:
        # No confirmations or timeout provided, directly get the receipt
        try:
            receipt = web3_instance.eth.get_transaction_receipt(tx_hash)
            return receipt
        except TransactionNotFound:
            return None
        
        except Exception as e:
            print("Error getting transaction receipt")
            raise e

def is_defined(val):
    return val is not None


async def is_arbitrum_chain(web3_instance):
    try:
        # Assuming you have the ABI for ArbSys in a JSON file
        with open('src/abi/ArbSys.json') as f:
            abi_content = json.load(f)
            ARBSYS_ABI = abi_content['abi'] if 'abi' in abi_content else abi_content

        if isinstance(web3_instance, ArbitrumProvider):
            provider = web3_instance.w3
        else:
            provider = web3_instance

        arb_sys_contract = provider.eth.contract(address=Web3.to_checksum_address(ARB_SYS_ADDRESS), abi=ARBSYS_ABI)
        arb_sys_contract.functions.arbOSVersion().call()
        return True
    except Exception:
        return False


async def get_first_block_for_l1_block(provider, for_l1_block, allow_greater=False, min_l2_block=None, max_l2_block='latest'):
    if not await is_arbitrum_chain(provider):
        return for_l1_block

    if isinstance(provider, ArbitrumProvider):
        arb_provider = provider
    else:
        arb_provider = ArbitrumProvider(provider)
    
    current_arb_block = arb_provider.w3.eth.get_block_number()
    arbitrum_chain_id = int(arb_provider.w3.net.version)
    nitro_genesis_block = l2_networks[arbitrum_chain_id].nitro_genesis_block
    
    async def get_l1_block(for_l2_block):
        block = await arb_provider.get_block(for_l2_block)
        return int(block["l1BlockNumber"], 16)

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



async def get_block_ranges_for_l1_block(provider, for_l1_block, min_l2_block=None, max_l2_block='latest', allow_greater=False):# -> list[None] | list:
    # arb_provider = ArbitrumProvider(provider)
    if isinstance(provider, ArbitrumProvider):
        arb_provider = provider
    else:
        arb_provider = ArbitrumProvider(provider)

    current_l2_block = arb_provider.w3.eth.block_number

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
