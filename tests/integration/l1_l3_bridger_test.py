import pytest
from eth_account import Account
import rlp
from web3 import Web3
from typing import Any, Callable, Optional
import time

from scripts.setup_common import get_local_networks_from_file, get_signer
from src.lib.asset_bridger.erc20_bridger import Erc20Bridger
from src.lib.asset_bridger.l1l3_bridger import (
    Erc20L1L3Bridger,
    EthL1L3Bridger,
    Erc20L1L3DepositRequestParams
)
from src.lib.data_entities.address import Address
from src.lib.data_entities.networks import (
    ArbitrumNetwork,
    assert_arbitrum_network_has_token_bridge,
    get_arbitrum_network,
    register_custom_arbitrum_network
)
from src.lib.message.parent_to_child_message import ParentToChildMessageStatus, ParentToChildMessageWriter
from src.lib.utils.helper import deploy_abi_contract, load_contract
from src.lib.utils.lib import get_native_token_decimals, is_defined
from scripts.test_setup import setup_testing_env
from tests.integration.test_helpers import fund_parent_signer, fund_child_signer
from tests.integration.custom_fee_token.custom_fee_token_test_helpers import is_arbitrum_network_with_custom_fee_token
from tests.integration.custom_fee_token.mocha_extensions import (
    it_only_when_custom_gas_token,
    it_only_when_eth
)

def expect_promise_to_reject(promise: Callable, expected_error: Optional[str] = None):
    """
    Helper to test if a promise/function rejects with expected error
    """
    error = None
    try:
        promise()
    except Exception as e:
        error = e

    if not error:
        raise Exception(f"Promise did not reject, expected: {expected_error}")
    
    if expected_error and str(error) != expected_error:
        raise Exception(
            f'Expected error "{expected_error}" but got "{str(error)}" instead'
        )

def hack_provider(provider: Web3, to: str, calldata: str, ret_data: str):
    """Mock provider call response for specific input"""
    original_call = provider.eth.call
    provider.original_call = original_call

    def mock_call(tx):
        if tx["to"] == to and tx["data"] == calldata:
            return ret_data
        return original_call(tx)

    provider.eth.call = mock_call

def unhack_provider(provider: Web3):
    """Restore original provider call behavior"""
    if hasattr(provider, "original_call"):
        provider.eth.call = provider.original_call

def poll(fn: Callable[[], bool], poll_interval: int) -> bool:
    """
    Poll a function until it returns True or errors
    """
    start_time = time.time()
    while True:
        try:
            result = fn()
            if result:
                return True
        except Exception as e:
            raise e
        
        if time.time() - start_time > 60:  # 1 minute timeout
            raise Exception("Poll timeout")
            
        time.sleep(poll_interval / 1000)  # Convert ms to seconds

def deploy_teleport_contracts(parent_signer: Any, child_signer: Any):
    """Deploy teleporter contracts"""
    # Predict the teleporter address
    nonce = parent_signer.provider.eth.get_transaction_count(
        parent_signer.account.address
    )
    pred_parent_teleporter = Web3.keccak(
        rlp.encode([parent_signer.account.address, nonce])
    )[12:]

    l2_contracts_deployer = deploy_abi_contract(
        provider=child_signer.provider,
        deployer=child_signer,
        contract_name="L2ForwarderContractsDeployer",
        constructor_args=[
            Address(pred_parent_teleporter).apply_alias().value,
            parent_signer.chain_id
        ]
    )

    parent_teleporter = deploy_abi_contract(
        provider=parent_signer.provider,
        deployer=parent_signer,
        contract_name="L1Teleporter",
        constructor_args=[
            l2_contracts_deployer.functions.factory().call(),
            l2_contracts_deployer.functions.implementation().call(),
            "0x" + "0" * 40,
            "0x" + "0" * 40
        ]
    )

    return {
        "parentTeleporter": parent_teleporter,
        "l2ContractsDeployer": l2_contracts_deployer
    }

def fund_actual_l1_custom_fee_token(
    parent_signer: Any,
    l2_fee_token: str, 
    l2_network: ArbitrumNetwork,
    l2_provider: Web3
):
    """Fund custom fee token on L1"""
    l1_fee_token = Erc20Bridger(l2_network).get_parent_erc20_address(
        l2_fee_token,
        l2_provider
    )

    deployer_wallet = get_signer(
        parent_signer.provider,
        Web3.keccak(text='user_fee_token_deployer').hex()
    )

    token_contract = load_contract(
        provider=deployer_wallet.provider,
        contract_name="ERC20",
        address=l1_fee_token
    )

    tx_hash = token_contract.functions.transfer(
        parent_signer.account.address,
        Web3.to_wei(10, "ether")
    ).transact({"from": deployer_wallet.account.address})

    deployer_wallet.provider.eth.wait_for_transaction_receipt(tx_hash)



@pytest.fixture(scope="module")
async def test_state():
    """Setup test state for all tests"""
    l2_network: ArbitrumNetwork = None
    l3_network: ArbitrumNetwork = None
    parent_signer = None
    child_signer = None
    l3_signer = None
    l3_provider = None

    if "ORBIT_TEST" not in os.environ or os.environ["ORBIT_TEST"] != "1":
        pytest.skip("Skipping as ORBIT_TEST is not enabled")

    setup = setup_testing_env()

    try:
        l2_network = get_arbitrum_network(setup["parentDeployer"])
    except Exception:
        local_networks = get_local_networks_from_file()
        l2_network = register_custom_arbitrum_network(local_networks["l2Network"])

    l3_network = setup["childChain"]

    parent_signer = get_signer(
        Web3(Web3.HTTPProvider(os.environ["ETH_URL"])),
        Account.create().key.hex()
    )
    child_signer = get_signer(
        Web3(Web3.HTTPProvider(os.environ["ARB_URL"])),
        Account.create().key.hex()
    )
    l3_provider = Web3(Web3.HTTPProvider(os.environ["ORBIT_URL"]))
    l3_signer = get_signer(
        l3_provider,
        Account.create().key.hex()
    )

    # Fund signers
    fund_parent_signer(parent_signer, Web3.to_wei(10, "ether"))
    fund_child_signer(child_signer, Web3.to_wei(10, "ether"))
    fund_child_signer(l3_signer, Web3.to_wei(10, "ether"))

    if is_arbitrum_network_with_custom_fee_token():
        await fund_actual_l1_custom_fee_token(
            parent_signer,
            l3_network.native_token,
            l2_network,
            child_signer.provider
        )

    return {
        "l2Network": l2_network,
        "l3Network": l3_network,
        "parentSigner": parent_signer,
        "childSigner": child_signer,
        "l3Signer": l3_signer,
        "l3Provider": l3_provider
    }

async def check_network_guards(
    l1: bool,
    l2: bool,
    l3: bool,
    check_function: Callable
):
    """Test network guard checks"""
    l1_chain_id = await parent_signer.chain_id
    l2_chain_id = await child_signer.chain_id
    l3_chain_id = l3_provider.eth.chain_id

    l3_signer = get_signer(
        l3_provider,
        Account.create().key.hex()
    )

    if l1:
        await expect_promise_to_reject(
            lambda: check_function(child_signer, child_signer, l3_signer),
            f"Signer/provider chain id: {l2_chain_id} doesn't match provided chain id: {l1_chain_id}."
        )

    if l2:
        await expect_promise_to_reject(
            lambda: check_function(parent_signer, parent_signer, l3_signer),
            f"Signer/provider chain id: {l1_chain_id} doesn't match provided chain id: {l2_chain_id}."
        )

    if l3:
        await expect_promise_to_reject(
            lambda: check_function(parent_signer, child_signer, parent_signer),
            f"Signer/provider chain id: {l1_chain_id} doesn't match provided chain id: {l3_chain_id}."
        )

    if is_arbitrum_network_with_custom_fee_token():
        await fund_actual_l1_custom_fee_token(
            parent_signer,
            l3_network.native_token,
            l2_network,
            child_signer.provider
        )


@pytest.mark.describe("L1 to L3 Bridging")
class TestL1ToL3Bridging:
    @pytest.fixture(autouse=True)
    def setup(self, test_state):
        if "ORBIT_TEST" not in os.environ or os.environ["ORBIT_TEST"] != "1":
            pytest.skip("Skipping as ORBIT_TEST is not enabled")
        self.test_state = test_state

    @pytest.mark.describe("EthL1L3Bridger")
    class TestEthL1L3Bridger:
        
        @it_only_when_eth
        def test_functions_should_be_guarded_by_check_network(self, test_state):
            """Test that functions are properly guarded by network checks"""
            l1_signer = test_state["parentSigner"]
            l2_signer = test_state["childSigner"]
            l3_signer = test_state["l3Signer"]
            l3_network = test_state["l3Network"]

            # Test getDepositRequest
            async def check_deposit_request(l1s, l2s, l3s):
                bridger = EthL1L3Bridger(l3_network)
                return await bridger.get_deposit_request({
                    "destinationAddress": l1s.account.address,
                    "amount": Web3.to_wei(0.1, "ether"),
                    "l1Signer": l1s,
                    "l2Provider": l2s.provider,
                    "l3Provider": l3s.provider,
                })

            check_network_guards(True, True, True, check_deposit_request)

            # Test deposit
            async def check_deposit(l1s, _l2s, _l3s):
                bridger = EthL1L3Bridger(l3_network)
                return await bridger.deposit({
                    "l1Signer": l1s,
                    "txRequest": {
                        "to": l1s.account.address,
                        "value": Web3.to_wei(0.1, "ether"),
                        "data": "0x"
                    }
                })

            check_network_guards(True, False, False, check_deposit)

            # Test getDepositStatus
            async def check_deposit_status(l1s, l2s, l3s):
                bridger = EthL1L3Bridger(l3_network)
                return await bridger.get_deposit_status({
                    "txReceipt": "",
                    "l1Provider": l1s.provider,
                    "l2Provider": l2s.provider,
                    "l3Provider": l3s.provider
                })

            check_network_guards(True, True, True, check_deposit_status)

        @it_only_when_custom_gas_token
        def test_should_fail_construction_if_l3_uses_custom_fee_token(self, test_state):
            """Test that construction fails for custom fee token networks"""
            l3_network = test_state["l3Network"]
            
            with pytest.raises(Exception) as exc_info:
                EthL1L3Bridger(l3_network)
            
            assert str(exc_info.value) == f"L3 network {l3_network.name} uses a custom fee token"

        @it_only_when_eth
        def test_happy_path(self, test_state):
            """Test complete ETH bridging flow"""
            l1_signer = test_state["parentSigner"]
            l2_signer = test_state["childSigner"]
            l3_provider = test_state["l3Provider"]
            l3_network = test_state["l3Network"]

            l1l3_bridger = EthL1L3Bridger(l3_network)
            l3_recipient = Account.create().address
            l2_refund_address = Account.create().address

            # Create deposit transaction
            deposit_tx = l1l3_bridger.deposit({
                "amount": Web3.to_wei(0.1, "ether"),
                "destinationAddress": l3_recipient,
                "l2RefundAddress": l2_refund_address,
                "l1Signer": l1_signer,
                "l2Provider": l2_signer.provider,
                "l3Provider": l3_provider
            })

            # Wait for transaction receipt
            deposit_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(deposit_tx)

            # Poll for completion
            def check_status():
                status = l1l3_bridger.get_deposit_status({
                    "txReceipt": deposit_receipt,
                    "l1Provider": l1_signer.provider,
                    "l2Provider": l2_signer.provider,
                    "l3Provider": l3_provider
                })
                return status.completed

            poll(check_status, 1000)

            # Verify balances
            l3_balance = l3_provider.eth.get_balance(l3_recipient)
            assert l3_balance > Web3.to_wei(0.1, "ether"), "L3 balance not updated correctly"

            l2_balance = l2_signer.provider.eth.get_balance(l2_refund_address)
            assert l2_balance > 0, "L2 refund balance not updated"


@pytest.mark.describe("ERC20 Bridging")
class TestERC20Bridging:
    @pytest.fixture(scope="class")
    def setup_erc20(self, test_state):
        """Setup ERC20 test environment"""
        # Deploy teleporter contracts and mock token
        parent_signer = test_state["parentSigner"]
        child_signer = test_state["childSigner"]
        
        # Deploy contracts
        contracts = deploy_teleport_contracts(parent_signer, child_signer)
        l2_network = test_state["l2Network"]
        l2_forwarder_factory = contracts["l2ContractsDeployer"].functions.factory().call()
        
        # Set teleporter on l2Network
        l2_network.teleporter = {
            "l1Teleporter": contracts["parentTeleporter"].address,
            "l2ForwarderFactory": l2_forwarder_factory
        }

        # Deploy mock token
        parent_token = deploy_abi_contract(
            provider=parent_signer.provider,
            deployer=parent_signer.account,
            contract_name="TestERC20",
        )
        
        tx_hash = parent_token.functions.mint().transact({"from": parent_signer.account.address})
        parent_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        # Create bridger
        l1l3_bridger = Erc20L1L3Bridger(test_state["l3Network"])
        
        return {
            **test_state,
            "parentToken": parent_token,
            "l1l3Bridger": l1l3_bridger,
            "amount": 100  # Equivalent to BigNumber.from(100)
        }

    @it_only_when_custom_gas_token
    def test_should_properly_get_l2_and_l1_fee_token_addresses(self, setup_erc20):
        """Test getting L1 and L2 fee token addresses"""
        l1_signer = setup_erc20["parentSigner"]
        l3_network = setup_erc20["l3Network"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]

        decimals = get_native_token_decimals(
            parent_provider=l1_signer.provider,
            child_network=l3_network
        )

        if decimals != 18:
            pytest.skip("Test only for 18 decimal tokens")

        assert l1l3_bridger.l2_gas_token_address is not None, "L2 fee token address is undefined"
        assert l1l3_bridger.l2_gas_token_address == l3_network.native_token, "L2 token doesn't equal L3 native token"

        # Verify L1 token maps to L2 token
        l1_gas_token = l1l3_bridger.get_gas_token_on_l1(
            l1_signer.provider,
            setup_erc20["childSigner"].provider
        )
        assert l1_gas_token is not None

        l2_mapped_token = Erc20Bridger(setup_erc20["l2Network"]).get_child_erc20_address(
            l1_gas_token,
            l1_signer.provider
        )
        assert l2_mapped_token == l1l3_bridger.l2_gas_token_address

    @it_only_when_custom_gas_token
    def test_should_throw_getting_l1_gas_token_address_when_unavailable(self, setup_erc20):
        """Test error when L1 gas token is unavailable"""
        l1_signer = setup_erc20["parentSigner"]
        l3_network = setup_erc20["l3Network"]

        decimals = get_native_token_decimals(
            parent_provider=l1_signer.provider,
            child_network=l3_network
        )

        if decimals != 18:
            pytest.skip("Test only for 18 decimal tokens")

        # Create modified network with random token address
        network_copy = copy.deepcopy(l3_network)
        network_copy.native_token = Account.create().address

        bridger = Erc20L1L3Bridger(network_copy)
        
        with pytest.raises(Exception) as exc_info:
            bridger.get_gas_token_on_l1(
                l1_signer.provider,
                setup_erc20["childSigner"].provider
            )
        
        assert str(exc_info.value) == "L1 gas token not found. Use skipGasToken when depositing"

    def test_get_l2_erc20_address(self, setup_erc20):
        """Test getting L2 ERC20 address"""
        l2_network = setup_erc20["l2Network"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        l1_signer = setup_erc20["parentSigner"]

        assert_arbitrum_network_has_token_bridge(l2_network)
        
        # Test with WETH addresses
        parent_weth = l2_network.token_bridge.parent_weth
        child_weth = l2_network.token_bridge.child_weth
        
        result = l1l3_bridger.get_l2_erc20_address(
            parent_weth,
            l1_signer.provider
        )
        
        assert result == child_weth

    def test_get_l1l2_gateway_address(self, setup_erc20):
        """Test getting L1-L2 gateway addresses"""
        l2_network = setup_erc20["l2Network"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        parent_token = setup_erc20["parentToken"]
        l1_signer = setup_erc20["parentSigner"]

        assert_arbitrum_network_has_token_bridge(l2_network)

        # Test WETH gateway
        parent_weth = l2_network.token_bridge.parent_weth
        parent_weth_gateway = l2_network.token_bridge.parent_weth_gateway

        weth_result = l1l3_bridger.get_l1l2_gateway_address(
            parent_weth,
            l1_signer.provider
        )
        assert weth_result == parent_weth_gateway

        # Test default gateway
        parent_gateway = l2_network.token_bridge.parent_erc20_gateway
        default_result = l1l3_bridger.get_l1l2_gateway_address(
            parent_token.address,
            l1_signer.provider
        )
        assert default_result == parent_gateway



@it_only_when_eth
    def test_get_l3_erc20_address(self, setup_erc20):
        """Test getting L3 ERC20 address mapping"""
        l2_network = setup_erc20["l2Network"]
        l3_network = setup_erc20["l3Network"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        l1_signer = setup_erc20["parentSigner"]
        l2_signer = setup_erc20["childSigner"]

        assert_arbitrum_network_has_token_bridge(l2_network)
        assert_arbitrum_network_has_token_bridge(l3_network)

        # Test with WETH addresses
        parent_weth = l2_network.token_bridge.parent_weth
        l3_weth = l3_network.token_bridge.child_weth

        result = l1l3_bridger.get_l3_erc20_address(
            parent_weth,
            l1_signer.provider,
            l2_signer.provider
        )
        
        assert result == l3_weth

    @it_only_when_eth
    def test_get_l2l3_gateway_address(self, setup_erc20):
        """Test getting L2-L3 gateway address mapping"""
        l2_network = setup_erc20["l2Network"]
        l3_network = setup_erc20["l3Network"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        parent_token = setup_erc20["parentToken"]
        l1_signer = setup_erc20["parentSigner"]
        l2_signer = setup_erc20["childSigner"]

        assert_arbitrum_network_has_token_bridge(l2_network)
        assert_arbitrum_network_has_token_bridge(l3_network)

        # Test WETH gateway
        parent_weth = l2_network.token_bridge.parent_weth
        l2l3_weth_gateway = l3_network.token_bridge.parent_weth_gateway

        weth_result = l1l3_bridger.get_l2l3_gateway_address(
            parent_weth,
            l1_signer.provider,
            l2_signer.provider
        )
        assert weth_result == l2l3_weth_gateway

        # Test default gateway
        l2l3_gateway = l3_network.token_bridge.parent_erc20_gateway
        default_result = l1l3_bridger.get_l2l3_gateway_address(
            parent_token.address,
            l1_signer.provider,
            l2_signer.provider
        )
        assert default_result == l2l3_gateway

    def test_approves(self, setup_erc20):
        """Test token approvals"""
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        parent_token = setup_erc20["parentToken"]
        l1_signer = setup_erc20["parentSigner"]

        # Approve the teleporter
        tx_hash = l1l3_bridger.approve_token({
            "erc20L1Address": parent_token.address,
            "l1Signer": l1_signer,
        })
        l1_signer.provider.eth.wait_for_transaction_receipt(tx_hash)

        allowance = parent_token.functions.allowance(
            l1_signer.account.address,
            l1l3_bridger.teleporter["l1Teleporter"]
        ).call()

        assert allowance == 2**256 - 1  # MAX_UINT256

    def test_functions_should_be_guarded_by_check_network(self, setup_erc20):
        """Test that functions are properly guarded by network checks"""
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        parent_token = setup_erc20["parentToken"]
        amount = setup_erc20["amount"]

        # Test l1FeeTokenAddress
        if is_arbitrum_network_with_custom_fee_token():
            check_network_guards(
                True, True, False,
                lambda l1s, l2s, _: l1l3_bridger.get_gas_token_on_l1(
                    l1s.provider,
                    l2s.provider
                )
            )

        # Test getL2Erc20Address
        check_network_guards(
            True, False, False,
            lambda l1s, _, _: l1l3_bridger.get_l2_erc20_address(
                parent_token.address,
                l1s.provider
            )
        )

        # Test getL3Erc20Address
        check_network_guards(
            True, True, False,
            lambda l1s, l2s, _: l1l3_bridger.get_l3_erc20_address(
                parent_token.address,
                l1s.provider,
                l2s.provider
            )
        )

        # Test getL1L2GatewayAddress
        check_network_guards(
            True, False, False,
            lambda l1s, _, _: l1l3_bridger.get_l1l2_gateway_address(
                parent_token.address,
                l1s.provider
            )
        )

        # Test getL2L3GatewayAddress
        check_network_guards(
            True, True, False,
            lambda l1s, l2s, _: l1l3_bridger.get_l2l3_gateway_address(
                parent_token.address,
                l1s.provider,
                l2s.provider
            )
        )

        # Test l1TokenIsDisabled
        check_network_guards(
            True, False, False,
            lambda l1s, _, _: l1l3_bridger.l1_token_is_disabled(
                parent_token.address,
                l1s.provider
            )
        )

        # Test l2TokenIsDisabled
        check_network_guards(
            False, True, False,
            lambda _, l2s, _: l1l3_bridger.l2_token_is_disabled(
                parent_token.address,
                l2s.provider
            )
        )

        # Test approveToken
        check_network_guards(
            True, False, False,
            lambda l1s, _, _: l1l3_bridger.approve_token({
                "txRequest": {
                    "to": parent_token.address,
                    "value": amount,
                    "data": "0x"
                },
                "l1Signer": l1s
            })
        )

        # Test other functions...
        # Continue with remaining function checks...


@it_only_when_custom_gas_token
    def test_happy_path_skip_fee_token(self, setup_erc20):
        """Test complete flow skipping fee token"""
        l1_signer = setup_erc20["parentSigner"]
        l2_signer = setup_erc20["childSigner"]
        l3_provider = setup_erc20["l3Provider"]
        l3_signer = setup_erc20["l3Signer"]
        parent_token = setup_erc20["parentToken"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        amount = setup_erc20["amount"]

        # Create random L3 recipient
        l3_recipient = Account.create().address

        deposit_params = {
            "erc20L1Address": parent_token.address,
            "destinationAddress": l3_recipient,
            "amount": amount,
            "l2Provider": l2_signer.provider,
            "l3Provider": l3_provider,
            "skipGasToken": True
        }

        # Get deposit request
        deposit_tx_request = l1l3_bridger.get_deposit_request({
            **deposit_params,
            "l1Signer": l1_signer
        })

        assert deposit_tx_request["gasTokenAmount"] == 0

        # Submit deposit
        deposit_tx = l1l3_bridger.deposit({
            "l1Signer": l1_signer,
            "txRequest": deposit_tx_request["txRequest"]
        })
        deposit_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(deposit_tx)

        # Poll for status
        def check_status():
            status = l1l3_bridger.get_deposit_status({
                "txHash": deposit_receipt["transactionHash"],
                "l1Provider": l1_signer.provider,
                "l2Provider": l2_signer.provider,
                "l3Provider": l3_provider
            })
            
            if not status.l2l3_token_bridge_retryable:
                return False
                
            retryable_status = status.l2l3_token_bridge_retryable.status()
            return retryable_status == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD

        poll(check_status, 1000)

        # Manually redeem L3 retryable
        status = l1l3_bridger.get_deposit_status({
            "txHash": deposit_receipt["transactionHash"],
            "l1Provider": l1_signer.provider,
            "l2Provider": l2_signer.provider,
            "l3Provider": l3_provider
        })

        ticket = status.l2l3_token_bridge_retryable
        assert ticket is not None

        message_writer = ParentToChildMessageWriter(
            l3_signer,
            setup_erc20["l3Network"].chain_id,
            ticket.sender,
            ticket.message_number,
            ticket.parent_base_fee,
            ticket.message_data
        )

        redeem_tx = message_writer.redeem({"gasLimit": 20_000_000})
        l3_signer.provider.eth.wait_for_transaction_receipt(redeem_tx)

        # Verify tokens landed in right place
        l3_token_addr = l1l3_bridger.get_l3_erc20_address(
            parent_token.address,
            l1_signer.provider,
            l2_signer.provider
        )
        l3_token = l1l3_bridger.get_l3_token_contract(l3_token_addr, l3_provider)

        l3_balance = l3_token.functions.balanceOf(l3_recipient).call()
        assert l3_balance == amount, "Token amount not correctly bridged"

    def test_happy_path_with_eth(self, setup_erc20):
        """Test complete flow with ETH"""
        l1_signer = setup_erc20["parentSigner"]
        l2_signer = setup_erc20["childSigner"]
        l3_provider = setup_erc20["l3Provider"]
        parent_token = setup_erc20["parentToken"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        amount = setup_erc20["amount"]

        l3_recipient = Account.create().address
        extra_eth = Web3.to_wei(0.0005, "ether")

        deposit_params = {
            "erc20L1Address": parent_token.address,
            "destinationAddress": l3_recipient,
            "amount": amount,
            "ethValue": extra_eth,
            "l2Provider": l2_signer.provider,
            "l3Provider": l3_provider
        }

        tx_request = l1l3_bridger.get_deposit_request({
            **deposit_params,
            "l1Signer": l1_signer
        })

        deposit_tx = l1l3_bridger.deposit({
            "l1Signer": l1_signer,
            "txRequest": tx_request["txRequest"]
        })
        
        deposit_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(deposit_tx)

        def check_completion():
            status = l1l3_bridger.get_deposit_status({
                "txHash": deposit_receipt["transactionHash"],
                "l1Provider": l1_signer.provider,
                "l2Provider": l2_signer.provider,
                "l3Provider": l3_provider
            })
            return status.completed

        poll(check_completion, 1000)

        # Verify balances
        l3_token_addr = l1l3_bridger.get_l3_erc20_address(
            parent_token.address,
            l1_signer.provider,
            l2_signer.provider
        )
        l3_token = l1l3_bridger.get_l3_token_contract(l3_token_addr, l3_provider)

        # Check token balance
        token_balance = l3_token.functions.balanceOf(l3_recipient).call()
        assert token_balance == amount, "Token amount not bridged correctly"

        # Check ETH balance
        eth_balance = l3_provider.eth.get_balance(l3_recipient)
        assert eth_balance >= extra_eth, "ETH not bridged correctly"

    def test_happy_path_with_eth_to_specific_address(self, setup_erc20):
        """Test bridging with ETH to specific L3 address"""
        l1_signer = setup_erc20["parentSigner"]
        l2_signer = setup_erc20["childSigner"]
        l3_provider = setup_erc20["l3Provider"]
        parent_token = setup_erc20["parentToken"]
        l1l3_bridger = setup_erc20["l1l3Bridger"]
        amount = setup_erc20["amount"]

        random_address = Account.create().address
        eth_deposit = Web3.to_wei(0.0005, "ether")

        deposit_request = l1l3_bridger.get_deposit_request({
            "erc20L1Address": parent_token.address,
            "destinationAddress": random_address,
            "amount": amount,
            "ethValue": eth_deposit,
            "l2Provider": l2_signer.provider,
            "l3Provider": l3_provider
        })

        deposit_tx = l1l3_bridger.deposit({
            "l1Signer": l1_signer,
            "txRequest": deposit_request["txRequest"]
        })
        
        deposit_receipt = l1_signer.provider.eth.wait_for_transaction_receipt(deposit_tx)

        def check_completion():
            status = l1l3_bridger.get_deposit_status({
                "txHash": deposit_receipt["transactionHash"],
                "l1Provider": l1_signer.provider,
                "l2Provider": l2_signer.provider,
                "l3Provider": l3_provider
            })
            return status.completed

        poll(check_completion, 1000)

        # Verify correct destination
        l3_token_addr = l1l3_bridger.get_l3_erc20_address(
            parent_token.address,
            l1_signer.provider,
            l2_signer.provider
        )
        l3_token = l1l3_bridger.get_l3_token_contract(l3_token_addr, l3_provider)

        token_balance = l3_token.functions.balanceOf(random_address).call()
        assert token_balance == amount, "Token amount not bridged to correct address"

        eth_balance = l3_provider.eth.get_balance(random_address)
        assert eth_balance >= eth_deposit, "ETH not bridged to correct address"