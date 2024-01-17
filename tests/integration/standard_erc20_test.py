import unittest
from web3 import Web3
from src.lib.utils.helper import load_contract
from src.lib.data_entities.constants import ARB_RETRYABLE_TX_ADDRESS, NODE_INTERFACE_ADDRESS
from .test_helpers import deposit_token, fund_l1, fund_l2, skip_if_mainnet, GatewayType, withdraw_token
from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.l2_transaction import L2TransactionReceipt
from src.lib.message.l1_to_l2_message import L1ToL2MessageWriter, L1ToL2MessageStatus
from src.scripts.test_setup import test_setup
from src.lib.utils.lib import is_defined
import pytest
import json
from web3 import Account
pytestmark = pytest.mark.asyncio


with open('src/abi/classic/TestERC20.json', 'r') as contract_file:
    contract_data = json.load(contract_file)

# Constants similar to depositAmount and withdrawalAmount
DEPOSIT_AMOUNT = Web3.to_wei(100, 'ether')
WITHDRAWAL_AMOUNT = Web3.to_wei(10, 'ether')


TEST_ERC20_ABI = contract_data['abi']
TEST_ERC20_BYTECODE = contract_data['bytecode']

# import { TestERC20 } from '../../src/lib/abi/TestERC20'
# import { ERC20__factory } from '../../src/lib/abi/factories/ERC20__factory'
# import { ArbRetryableTx__factory } from '../../src/lib/abi/factories/ArbRetryableTx__factory'
# import { NodeInterface__factory } from '../../src/lib/abi/factories/NodeInterface__factory'



# class TestERC20(unittest.TestCase):

    # def setUp(self):
    #     # Setup code here. Replace with actual setup.
    #     self.l1Signer = Web3(HTTPProvider('http://localhost:8545')).eth.accounts[0]  # Placeholder
    #     self.l2Signer = Web3(HTTPProvider('http://localhost:8547')).eth.accounts[0]  # Placeholder
    #     self.erc20Bridger = ERC20Bridger()  # Replace with actual initialization
    #     self.l2Network = L2Network()  # Replace with actual initialization
    #     self.l1Token = load_contract(Web3(HTTPProvider('http://localhost:8545')), 'TestERC20', TEST_ERC20_ADDRESS)

    # def test_deposit_erc20(self):
    #     # Replace with actual deposit_token function
    #     deposit_amount = Web3.to_wei(100, 'ether')
    #     deposit_token(deposit_amount, self.l1Token.address, self.erc20Bridger, self.l1Signer, self.l2Signer, L1ToL2MessageStatus.REDEEMED, GatewayType.STANDARD)

    # def test_deposit_with_no_funds_manual_redeem(self):
    #     deposit_amount = Web3.to_wei(100, 'ether')
    #     wait_res = deposit_token(deposit_amount, self.l1Token.address, self.erc20Bridger, self.l1Signer, self.l2Signer, L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2, GatewayType.STANDARD, gas_limit=0, max_fee_per_gas=0)
    #     # Replace redeemAndTest with actual implementation.
    #     self.redeemAndTest(wait_res['message'], 1)

    # def test_deposit_with_low_funds_manual_redeem(self):
    #     deposit_amount = Web3.to_wei(100, 'ether')
    #     wait_res = deposit_token(deposit_amount, self.l1Token.address, self.erc20Bridger, self.l1Signer, self.l2Signer, L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2, GatewayType.STANDARD, gas_limit=5, max_fee_per_gas=5)
    #     self.redeemAndTest(wait_res['message'], 1)


# class StandardERC20Test(unittest.TestCase):
    
    # @pytest.mark.asyncio
    # async def setUpClass(cls):
    #     cls.setup = await test_setup()
    #     fund_l1(cls.setup['l1Signer'])
    #     fund_l2(cls.setup['l2Signer'])

    #     cls.deploy_erc20 = load_contract(cls.setup['l1Signer'].provider, 'TestERC20', cls.setup['l1Token'].address, is_classic=True)
    #     cls.test_token = cls.deploy_erc20.deploy(cls.setup['l1Signer'])
    #     cls.test_token.deployed()
    #     cls.test_token.mint().wait()

    #     cls.test_state = cls.setup
    #     cls.test_state['l1Token'] = cls.test_token


def deploy_test_erc20(web3_instance, deployer):
    # Create the contract instance
    contract = web3_instance.eth.contract(abi=TEST_ERC20_ABI, bytecode=TEST_ERC20_BYTECODE)
    
    # deployer = Account.from_key(deployer_private_key)
    # Fetch the current chain ID for EIP-155 replay protection
    chain_id = web3_instance.eth.chain_id

    # Estimate the gas required for deployment
    gas_estimate = contract.constructor().estimate_gas({'from': deployer.address})

    # Build the deployment transaction
    construct_txn = contract.constructor().build_transaction({
        'from': deployer.address,
        'nonce': web3_instance.eth.get_transaction_count(deployer.address),
        'gas': gas_estimate,  # Use the estimated gas limit
        'gasPrice': web3_instance.eth.gas_price,
        'chainId': chain_id  # Include the chain ID
    })

    signed_txn = deployer.sign_transaction(construct_txn)

    # Send the transaction
    tx_hash = web3_instance.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = web3_instance.eth.wait_for_transaction_receipt(tx_hash)

    # Get the contract address
    contract_address = tx_receipt.contractAddress
    return contract_address


def mint_tokens(web3_instance, contract_address, minter):
    # Create the contract instance
    contract = web3_instance.eth.contract(address=contract_address, abi=TEST_ERC20_ABI)

    # minter = Account.from_key(minter_private_key)

    # Fetch the current chain ID for EIP-155 replay protection
    chain_id = web3_instance.eth.chain_id

    # Build the mint transaction
    mint_txn = contract.functions.mint().build_transaction({
    'from': minter.address,
    'nonce': web3_instance.eth.get_transaction_count(minter.address),
    # 'gas': gas_estimate, # Set appropriate gas limit
    'gasPrice': web3_instance.eth.gas_price,
    'chainId': chain_id  # Include the chain ID
    })

    # Estimate gas for the mint transaction
    mint_txn['gas'] = web3_instance.eth.estimate_gas(mint_txn)

    # Sign the transaction
    signed_txn = minter.sign_transaction(mint_txn)

    # Send the transaction
    tx_hash = web3_instance.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = web3_instance.eth.wait_for_transaction_receipt(tx_hash)
    return tx_receipt



@pytest.fixture
async def setup_state():
    setup = await test_setup()
    # print(setup)
    fund_l1(setup.l1_provider, setup.l1_signer_account.address)
    fund_l2(setup.l2_provider, setup.l2_signer_account.address)

    contract_address = deploy_test_erc20(setup.l1_provider, setup.l1_signer_account)
    print('deployed_erc20_address', contract_address)
    
    # # Mint tokens
    mint_receipt = mint_tokens(setup.l1_provider, contract_address, setup.l1_signer_account)
    print('mint_receipt', mint_receipt)
    
    # # Add the contract address to the setup
    setup['l1_token_address'] = contract_address
    return setup



@pytest.mark.asyncio
async def test_deposit_erc20(setup_state) -> None:
    await deposit_token(
        l1_provider=setup_state.l1_provider,
        l2_provider=setup_state.l2_provider,
        deposit_amount=DEPOSIT_AMOUNT,
        l1_token_address=setup_state.l1_token_address,
        erc20_bridger=setup_state.erc20_bridger,
        l1_signer=setup_state.l1_signer_account,
        l2_signer=setup_state.l2_signer_account,
        expected_status=L1ToL2MessageStatus.REDEEMED,
        expected_gateway_type=GatewayType.STANDARD
    )

    # def redeem_and_test(self, message: L1ToL2MessageWriter, expected_status: int, gas_limit=None):
    #     manual_redeem = message.redeem(gas_limit)
    #     retry_rec = manual_redeem.wait_for_redeem()
    #     redeem_rec = manual_redeem.wait()
    #     block_hash = redeem_rec.block_hash

    #     self.assertEqual(retry_rec.block_hash, block_hash)
    #     self.assertEqual(retry_rec.to, self.test_state['l2Network'].tokenBridge.l2ERC20Gateway)
    #     self.assertEqual(retry_rec.status, expected_status)
    #     self.assertEqual(message.status(), expected_status)

    # def test_deposit_with_no_funds_manual_redeem(self):
    #     wait_res = deposit_token(
    #         Web3.to_wei(100, 'ether'),
    #         self.test_state['l1Token'].address,
    #         self.test_state['erc20Bridger'],
    #         self.test_state['l1Signer'],
    #         self.test_state['l2Signer'],
    #         L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
    #         GatewayType.STANDARD,
    #         gas_limit=0,
    #         max_fee_per_gas=0
    #     )

    #     self.redeem_and_test(wait_res.message, 1)


    # def test_deposit_with_low_funds_manual_redeem(self):
    #     wait_res = deposit_token(
    #         Web3.to_wei(100, 'ether'),
    #         self.test_state['l1Token'].address,
    #         self.test_state['erc20Bridger'],
    #         self.test_state['l1Signer'],
    #         self.test_state['l2Signer'],
    #         L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
    #         GatewayType.STANDARD,
    #         gas_limit=5,
    #         max_fee_per_gas=5
    #     )

    #     self.redeem_and_test(wait_res.message, 1)

    # def test_deposit_with_only_low_gas_limit_manual_redeem_succeeds(self):
    #     wait_res = deposit_token(
    #         Web3.to_wei(100, 'ether'),
    #         self.test_state['l1Token'].address,
    #         self.test_state['erc20Bridger'],
    #         self.test_state['l1Signer'],
    #         self.test_state['l2Signer'],
    #         L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
    #         GatewayType.STANDARD,
    #         gas_limit=21000
    #     )

    #     retryable_creation = wait_res.message.get_retryable_creation_receipt()
    #     if not is_defined(retryable_creation):
    #         raise ArbSdkError('Missing retryable creation.')

    #     l2_receipt = L2TransactionReceipt(retryable_creation)
    #     redeems_scheduled = l2_receipt.get_redeem_scheduled_events()
    #     self.assertEqual(len(redeems_scheduled), 1)

    #     retry_receipt = self.test_state['l2Signer'].provider.getTransactionReceipt(
    #         redeems_scheduled[0].retry_tx_hash
    #     )
    #     self.assertFalse(is_defined(retry_receipt))

    #     self.redeem_and_test(wait_res.message, 1)

    # def test_deposit_with_low_funds_fails_first_redeem_succeeds_seconds(self):
    #     wait_res = deposit_token(
    #         Web3.to_wei(100, 'ether'),
    #         self.test_state['l1Token'].address,
    #         self.test_state['erc20Bridger'],
    #         self.test_state['l1Signer'],
    #         self.test_state['l2Signer'],
    #         L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2,
    #         GatewayType.STANDARD,
    #         gas_limit=5,
    #         max_fee_per_gas=5
    #     )

    #     arb_retryable_tx = load_contract(self.test_state['l2Signer'].provider, 'ArbRetryableTx', ARB_RETRYABLE_TX_ADDRESS, is_classic=False)
    #     n_interface = load_contract(self.test_state['l2Signer'].provider, 'NodeInterface', NODE_INTERFACE_ADDRESS) # also available in classic!

    #     gas_components = n_interface.callStatic.gas_estimate_components(
    #         arb_retryable_tx.address,
    #         False,
    #         arb_retryable_tx.encode_function_data('redeem', [wait_res.message.retryable_creation_id])
    #     )

    #     self.redeem_and_test(wait_res.message, 0, gas_components['gas_estimate'] - 1000)
    #     self.redeem_and_test(wait_res.message, 1)

    # def test_withdraws_erc20(self):
    #     l2_token_addr = self.test_state['erc20Bridger'].get_l2_erc20_address(
    #         self.test_state['l1Token'].address,
    #         self.test_state['l1Signer'].provider
    #     )

    #     l2_token = self.test_state['erc20Bridger'].get_l2_token_contract(
    #         self.test_state['l2Signer'].provider,
    #         l2_token_addr
    #     )

    #     start_balance = Web3.to_wei(500, 'ether')  # 5 deposits in the previous tests
    #     l2_balance_start = l2_token.balance_of(self.test_state['l2Signer'].address)

    #     self.assertEqual(str(l2_balance_start), str(start_balance))

    #     withdraw_token(
    #         amount=Web3.to_wei(10, 'ether'),
    #         gateway_type=GatewayType.STANDARD,
    #         start_balance=start_balance,
    #         l1_token=load_contract(self.test_state['l1Signer'].provider, 'ERC20', self.test_state['l1Token'].address, is_classic=True),
    #         test_state=self.test_state
    #     )

    # def test_deposit_with_only_low_gas_limit_manual_redeem_succeeds(self):
    #     deposit_amount = Web3.to_wei(100, 'ether')
    #     wait_res = deposit_token(deposit_amount, self.l1Token.address, self.erc20Bridger, self.l1Signer, self.l2Signer, L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2, GatewayType.STANDARD, gas_limit=21000)

    #     # Assuming getRetryableCreationReceipt, getRedeemScheduledEvents, and getTransactionReceipt are implemented
    #     retryable_creation = wait_res['message'].get_retryable_creation_receipt()
    #     if not retryable_creation:
    #         raise Exception('Missing retryable creation.')
    #     l2_receipt = L2TransactionReceipt(retryable_creation)
    #     redeems_scheduled = l2_receipt.get_redeem_scheduled_events()
    #     self.assertEqual(len(redeems_scheduled), 1, 'Unexpected redeem length')
    #     retry_receipt = self.l2Signer.provider.getTransactionReceipt(redeems_scheduled[0].retry_tx_hash)
    #     self.assertFalse(retry_receipt, 'Retry should not exist')

    #     # manual redeem succeeds
    #     self.redeemAndTest(wait_res['message'], 1)

    # def test_deposit_with_low_funds_fails_first_redeem_succeeds_seconds(self):
    #     deposit_amount = Web3.to_wei(100, 'ether')
    #     wait_res = deposit_token(deposit_amount, self.l1Token.address, self.erc20Bridger, self.l1Signer, self.l2Signer, L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2, GatewayType.STANDARD, gas_limit=5, max_fee_per_gas=5)
    #     arb_retryable_tx = load_contract(self.l2Signer.provider, 'ArbRetryableTx', ARB_RETRYABLE_TX_ADDRESS)
    #     n_interface = load_contract(self.l2Signer.provider, 'NodeInterface', NODE_INTERFACE_ADDRESS)
    #     gas_components = n_interface.functions.gasEstimateComponents(
    #         arb_retryable_tx.address,
    #         False,
    #         arb_retryable_tx.functions.redeem(wait_res['message'].retryable_creation_id).encodeABI()
    #     ).call()

    #     # force the redeem to fail by submitting just a bit under the required gas
    #     self.redeemAndTest(wait_res['message'], 0, gas_components['gasEstimate'] - 1000)
    #     self.redeemAndTest(wait_res['message'], 1)

    # def test_withdraws_erc20(self):
    #     l2_token_addr = self.erc20Bridger.get_l2_erc20_address(self.l1Token.address, self.l1Signer.provider)
    #     l2_token = self.erc20Bridger.get_l2_token_contract(self.l2Signer.provider, l2_token_addr)
    #     start_balance = deposit_amount * 5  # 5 deposits above - increase this number if more deposit tests added
    #     l2_balance_start = l2_token.functions.balanceOf(self.l2Signer.address).call()
    #     self.assertEqual(l2_balance_start, start_balance, 'l2 balance start')

    #     withdraw_token({
    #         'testState': testState,
    #         'amount': withdrawalAmount,
    #         'gatewayType': GatewayType.STANDARD,
    #         'startBalance': start_balance,
    #         'l1Token': load_contract(self.l1Signer.provider, 'ERC20', self.l1Token.address),
    #     })
