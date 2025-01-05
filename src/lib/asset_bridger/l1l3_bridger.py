from typing import Union, Optional, Dict, Any, List
import os

from web3 import Web3
from web3.exceptions import ContractLogicError
from eth_utils import keccak

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import (
    ArbitrumNetwork,
    assert_arbitrum_network_has_token_bridge,
    get_arbitrum_networks,
)
from src.lib.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from src.lib.message.parent_transaction import (
    ParentContractCallTransaction,
    ParentContractCallTransactionReceipt,
    ParentEthDepositTransactionReceipt,
    ParentTransactionReceipt,
)
from src.lib.message.parent_to_child_message import (
    ParentToChildMessageReader,
    ParentToChildMessageStatus,
)
from src.lib.message.parent_to_child_message_creator import ParentToChildMessageCreator
from src.lib.message.parent_to_child_message_gas_estimator import (
    ParentToChildMessageGasEstimator,
)
from src.lib.asset_bridger.erc20_bridger import Erc20Bridger
from src.lib.utils.helper import create_contract_instance, load_contract, get_address

# ------------------------------------------------------------------------------------
# Data structures and “type” equivalents
# ------------------------------------------------------------------------------------

class TeleportationType:
    """
    Python equivalent of the TypeScript enum TeleportationType
    describing the type of teleportation:
      - Standard: Teleporting to an ETH-fee L3
      - OnlyGasToken: Teleporting the fee token to a custom-fee L3
      - NonGasTokenToCustomGas: Teleporting a non-fee token to a custom-fee L3
    """
    Standard = 0
    OnlyGasToken = 1
    NonGasTokenToCustomGas = 2


class RetryableGasValues:
    """
    Python representation of:
      type RetryableGasValues = {
        gasLimit: BigNumber
        maxSubmissionFee: BigNumber
      }
    Treated here as simple integers.
    """
    def __init__(self, gas_limit: int, max_submission_fee: int):
        self.gasLimit = gas_limit
        self.maxSubmissionFee = max_submission_fee


class TeleporterRetryableGasOverride:
    """
    Python representation of:
      type TeleporterRetryableGasOverride = {
        gasLimit?: PercentIncrease & { min?: BigNumber }
        maxSubmissionFee?: PercentIncrease
      }
    """
    def __init__(
        self,
        gas_limit: Optional[Dict[str, Any]] = None,
        max_submission_fee: Optional[Dict[str, Any]] = None,
    ):
        self.gasLimit = gas_limit
        self.maxSubmissionFee = max_submission_fee


class TokenApproveParams:
    """
    Python representation of:
      type TokenApproveParams = {
        erc20L1Address: string
        amount?: BigNumber
      }
    """
    def __init__(self, erc20_l1_address: str, amount: Optional[int] = None):
        self.erc20L1Address = erc20_l1_address
        self.amount = amount


class TxRequestParams:
    """
    Python representation of:
      export type TxRequestParams = {
        txRequest: PickedTransactionRequest
        l1Signer: Signer
        overrides?: PayableOverrides
      }
    """
    def __init__(
        self,
        tx_request: Dict[str, Any],
        l1_signer: Any,
        overrides: Optional[Dict[str, Any]] = None
    ):
        self.txRequest = tx_request
        self.l1Signer = l1_signer
        self.overrides = overrides


class DepositRequestResult:
    """
    Python representation of:
      export type DepositRequestResult = {
        txRequest: PickedTransactionRequest
        gasTokenAmount: BigNumber
      }
    """
    def __init__(self, tx_request: Dict[str, Any], gas_token_amount: int):
        self.txRequest = tx_request
        self.gasTokenAmount = gas_token_amount


class Erc20L1L3DepositRequestRetryableOverrides:
    """
    Python representation of:
      export type Erc20L1L3DepositRequestRetryableOverrides = {
        l1GasPrice?: PercentIncrease
        l2GasPrice?: PercentIncrease
        l3GasPrice?: PercentIncrease
        l2ForwarderFactoryRetryableGas?: TeleporterRetryableGasOverride
        l1l2GasTokenBridgeRetryableGas?: TeleporterRetryableGasOverride
        l1l2TokenBridgeRetryableGas?: TeleporterRetryableGasOverride
        l2l3TokenBridgeRetryableGas?: TeleporterRetryableGasOverride
      }
    """
    def __init__(
        self,
        l1GasPrice: Optional[Dict[str, Any]] = None,
        l2GasPrice: Optional[Dict[str, Any]] = None,
        l3GasPrice: Optional[Dict[str, Any]] = None,
        l2ForwarderFactoryRetryableGas: Optional[TeleporterRetryableGasOverride] = None,
        l1l2GasTokenBridgeRetryableGas: Optional[TeleporterRetryableGasOverride] = None,
        l1l2TokenBridgeRetryableGas: Optional[TeleporterRetryableGasOverride] = None,
        l2l3TokenBridgeRetryableGas: Optional[TeleporterRetryableGasOverride] = None,
    ):
        self.l1GasPrice = l1GasPrice
        self.l2GasPrice = l2GasPrice
        self.l3GasPrice = l3GasPrice
        self.l2ForwarderFactoryRetryableGas = l2ForwarderFactoryRetryableGas
        self.l1l2GasTokenBridgeRetryableGas = l1l2GasTokenBridgeRetryableGas
        self.l1l2TokenBridgeRetryableGas = l1l2TokenBridgeRetryableGas
        self.l2l3TokenBridgeRetryableGas = l2l3TokenBridgeRetryableGas


class Erc20L1L3DepositRequestParams:
    """
    Python representation of:
      export type Erc20L1L3DepositRequestParams = {
        erc20L1Address: string
        amount: BigNumber
        l2Provider: Provider
        l3Provider: Provider
        skipGasToken?: boolean
        destinationAddress?: string
        retryableOverrides?: Erc20L1L3DepositRequestRetryableOverrides
      }
    """
    def __init__(
        self,
        erc20L1Address: str,
        amount: int,
        l2Provider: Web3,
        l3Provider: Web3,
        skipGasToken: bool = False,
        destinationAddress: Optional[str] = None,
        retryableOverrides: Optional[Erc20L1L3DepositRequestRetryableOverrides] = None,
    ):
        self.erc20L1Address = erc20L1Address
        self.amount = amount
        self.l2Provider = l2Provider
        self.l3Provider = l3Provider
        self.skipGasToken = skipGasToken
        self.destinationAddress = destinationAddress
        self.retryableOverrides = retryableOverrides


class TxReference:
    """
    Pythonic approach to represent 'TxReference' from TS:
      type TxReference = { txHash: string } | { tx: ... } | { txReceipt: ... }
    """
    def __init__(
        self,
        txHash: Optional[str] = None,
        tx: Optional[ParentContractCallTransaction] = None,
        txReceipt: Optional[ParentContractCallTransactionReceipt] = None
    ):
        self.txHash = txHash
        self.tx = tx
        self.txReceipt = txReceipt


class GetL1L3DepositStatusParams(TxReference):
    """
    Python representation of:
      export type GetL1L3DepositStatusParams = { l1Provider: Provider; l2Provider: Provider; l3Provider: Provider } & TxReference
    """
    def __init__(
        self,
        l1Provider: Web3,
        l2Provider: Web3,
        l3Provider: Web3,
        txHash: Optional[str] = None,
        tx: Optional[ParentContractCallTransaction] = None,
        txReceipt: Optional[ParentContractCallTransactionReceipt] = None
    ):
        super().__init__(txHash, tx, txReceipt)
        self.l1Provider = l1Provider
        self.l2Provider = l2Provider
        self.l3Provider = l3Provider


class Erc20L1L3DepositStatus:
    """
    Python representation of:
      export type Erc20L1L3DepositStatus = {
        l1l2TokenBridgeRetryable: ParentToChildMessageReader
        l1l2GasTokenBridgeRetryable: ParentToChildMessageReader | undefined
        l2ForwarderFactoryRetryable: ParentToChildMessageReader
        l2l3TokenBridgeRetryable: ParentToChildMessageReader | undefined
        l2ForwarderFactoryRetryableFrontRan: boolean
        completed: boolean
      }
    """
    def __init__(
        self,
        l1l2TokenBridgeRetryable: ParentToChildMessageReader,
        l2ForwarderFactoryRetryable: ParentToChildMessageReader,
        completed: bool,
        l1l2GasTokenBridgeRetryable: Optional[ParentToChildMessageReader] = None,
        l2l3TokenBridgeRetryable: Optional[ParentToChildMessageReader] = None,
        l2ForwarderFactoryRetryableFrontRan: bool = False,
    ):
        self.l1l2TokenBridgeRetryable = l1l2TokenBridgeRetryable
        self.l1l2GasTokenBridgeRetryable = l1l2GasTokenBridgeRetryable
        self.l2ForwarderFactoryRetryable = l2ForwarderFactoryRetryable
        self.l2l3TokenBridgeRetryable = l2l3TokenBridgeRetryable
        self.l2ForwarderFactoryRetryableFrontRan = l2ForwarderFactoryRetryableFrontRan
        self.completed = completed


class EthL1L3DepositRequestParams:
    """
    Python representation of:
      export type EthL1L3DepositRequestParams = {
        amount: BigNumberish
        l2Provider: Provider
        l3Provider: Provider
        destinationAddress?: string
        l2RefundAddress?: string
        l2TicketGasOverrides?: Omit<GasOverrides, 'deposit'>
        l3TicketGasOverrides?: Omit<GasOverrides, 'deposit'>
      }
    """
    def __init__(
        self,
        amount: int,
        l2Provider: Web3,
        l3Provider: Web3,
        destinationAddress: Optional[str] = None,
        l2RefundAddress: Optional[str] = None,
        l2TicketGasOverrides: Optional[Dict[str, Any]] = None,
        l3TicketGasOverrides: Optional[Dict[str, Any]] = None,
    ):
        self.amount = amount
        self.l2Provider = l2Provider
        self.l3Provider = l3Provider
        self.destinationAddress = destinationAddress
        self.l2RefundAddress = l2RefundAddress
        self.l2TicketGasOverrides = l2TicketGasOverrides
        self.l3TicketGasOverrides = l3TicketGasOverrides


class EthL1L3DepositStatus:
    """
    Python representation of:
      export type EthL1L3DepositStatus = {
        l2Retryable: ParentToChildMessageReader
        l3Retryable: ParentToChildMessageReader | undefined
        completed: boolean
      }
    """
    def __init__(
        self,
        l2Retryable: ParentToChildMessageReader,
        completed: bool,
        l3Retryable: Optional[ParentToChildMessageReader] = None
    ):
        self.l2Retryable = l2Retryable
        self.l3Retryable = l3Retryable
        self.completed = completed


# ------------------------------------------------------------------------------------
# Base class: BaseL1L3Bridger
# ------------------------------------------------------------------------------------

class BaseL1L3Bridger:
    """
    Python equivalent of the TypeScript 'BaseL1L3Bridger' class,
    which provides base functionality for bridging from L1 to L3.
    """

    def __init__(self, l3_network: ArbitrumNetwork):
        """
        :param l3_network: The ArbitrumNetwork describing the L3 chain.
        :raises ArbSdkError: If we cannot find the L2 network for l3_network.parentChainId
        """
        potential_l2 = None
        for net in get_arbitrum_networks():
            if net.chainId == l3_network.parentChainId:
                potential_l2 = net
                break

        if not potential_l2:
            raise ArbSdkError(
                f"Unknown Arbitrum network chain id: {l3_network.parentChainId}"
            )

        # Keep references:
        self.l2Network = potential_l2
        self.l1Network = {"chainId": potential_l2.parentChainId}
        self.l3Network = l3_network

        self.defaultGasPricePercentIncrease = 500
        self.defaultGasLimitPercentIncrease = 100

    def _check_l1_network(self, sop: SignerOrProvider):
        """
        Ensure the signer/provider is on the expected L1 chainId.
        """
        SignerProviderUtils.check_network_matches(
            sop, self.l1Network["chainId"]
        )

    def _check_l2_network(self, sop: SignerOrProvider):
        """
        Ensure the signer/provider is on the expected L2 chainId.
        """
        SignerProviderUtils.check_network_matches(
            sop, self.l2Network.chainId
        )

    def _check_l3_network(self, sop: SignerOrProvider):
        """
        Ensure the signer/provider is on the expected L3 chainId.
        """
        SignerProviderUtils.check_network_matches(
            sop, self.l3Network.chainId
        )

    def _percent_increase(self, num: int, increase: int) -> int:
        """
        :param num: The base integer
        :param increase: The percent to increase by
        """
        return num + (num * increase) // 100

    def _get_tx_hash_from_tx_ref(self, tx_ref: Union[Dict[str, Any], "TxReference"]) -> str:
        """
        Utility to retrieve the transaction hash from a TxReference-like object.
        """
        if "txHash" in tx_ref:
            return tx_ref["txHash"]
        elif "tx" in tx_ref:
            return tx_ref["tx"].hash
        else:
            return tx_ref["txReceipt"].transactionHash

    def _get_tx_from_tx_ref(
        self,
        tx_ref: Union[Dict[str, Any], "TxReference"],
        provider: Web3
    ) -> ParentContractCallTransaction:
        """
        If 'tx' key is present, return that. 
        Otherwise fetch from chain and monkey-patch.
        """
        if "tx" in tx_ref:
            return tx_ref["tx"]

        tx_hash = self._get_tx_hash_from_tx_ref(tx_ref)
        raw_tx = provider.eth.get_transaction(tx_hash)
        return ParentTransactionReceipt.monkey_patch_contract_call_wait(raw_tx)

    def _get_tx_receipt_from_tx_ref(
        self,
        tx_ref: Union[Dict[str, Any], "TxReference"],
        provider: Web3
    ) -> ParentContractCallTransactionReceipt:
        """
        If 'txReceipt' key is present, return that.
        Otherwise fetch from chain by transaction hash.
        """
        if "txReceipt" in tx_ref:
            return tx_ref["txReceipt"]

        tx_hash = self._get_tx_hash_from_tx_ref(tx_ref)
        receipt = provider.eth.get_transaction_receipt(tx_hash)
        return ParentContractCallTransactionReceipt(receipt)


# ------------------------------------------------------------------------------------
# Erc20L1L3Bridger
# ------------------------------------------------------------------------------------

class Erc20L1L3Bridger(BaseL1L3Bridger):
    """
    Python version of the Erc20L1L3Bridger from l1l3Bridger.ts
    """

    def __init__(self, l3_network: ArbitrumNetwork):
        super().__init__(l3_network)

        if not self.l2Network.teleporter:
            raise ArbSdkError(
                f"L2 network {self.l2Network.name} does not have teleporter contracts"
            )

        # Hardcode default gas limit
        self.l2ForwarderFactoryDefaultGasLimit = 1_000_000

        # Replicate skipL1GasTokenMagic: keccak("SKIP_FEE_TOKEN")[0..20]
        hashed = keccak(text="SKIP_FEE_TOKEN")
        raw_20 = hashed[:20]
        self.skipL1GasTokenMagic = Web3.toChecksumAddress("0x" + raw_20.hex())

        # If L3 uses a custom fee token:
        if (
            self.l3Network.nativeToken
            and self.l3Network.nativeToken != "0x0000000000000000000000000000000000000000"
        ):
            self.l2GasTokenAddress: Optional[str] = self.l3Network.nativeToken
        else:
            self.l2GasTokenAddress = None

        self.teleporter = self.l2Network.teleporter

        # Erc20Bridger for L2 and L3
        self.l2Erc20Bridger = Erc20Bridger(self.l2Network)
        self.l3Erc20Bridger = Erc20Bridger(self.l3Network)

        self._l1FeeTokenAddress: Optional[str] = None

    def get_gas_token_on_l1(self, l1_provider: Web3, l2_provider: Web3) -> str:
        """
        Equivalent to getGasTokenOnL1 in TS
        """
        if not self.l2GasTokenAddress:
            raise ArbSdkError("L3 uses ETH for gas")

        if self._l1FeeTokenAddress is not None:
            return self._l1FeeTokenAddress

        self._check_l1_network(l1_provider)
        self._check_l2_network(l2_provider)

        l1_fee_token_address: Optional[str] = None

        try:
            l1_fee_token_address = self.l2Erc20Bridger.get_parent_erc20_address(
                self.l2GasTokenAddress,
                l2_provider
            )
        except ContractLogicError as e:
            # If not a call exception, re-raise
            if e.args and "CALL_EXCEPTION" not in str(e):
                raise e

        if not l1_fee_token_address or l1_fee_token_address == "0x0000000000000000000000000000000000000000":
            raise ArbSdkError("L1 gas token not found. Use skipGasToken when depositing")

        # Check decimals = 18 on L1
        l1_contract = load_contract(l1_provider, "ERC20", address=l1_fee_token_address)
        decimals_l1 = l1_contract.functions.decimals().call()
        if decimals_l1 != 18:
            raise ArbSdkError("L1 gas token has incorrect decimals. Use skipGasToken when depositing")

        # Check decimals = 18 on L2
        l2_contract = load_contract(l2_provider, "ERC20", address=self.l2GasTokenAddress)
        decimals_l2 = l2_contract.functions.decimals().call()
        if decimals_l2 != 18:
            raise ArbSdkError("L2 gas token has incorrect decimals. Use skipGasToken when depositing")

        if self.l1_token_is_disabled(l1_fee_token_address, l1_provider):
            raise ArbSdkError(
                "L1 gas token is disabled on the L1->L2 token bridge. Use skipGasToken when depositing"
            )
        if self.l2_token_is_disabled(self.l2GasTokenAddress, l2_provider):
            raise ArbSdkError(
                "L2 gas token is disabled on the L2->L3 token bridge. Use skipGasToken when depositing"
            )

        self._l1FeeTokenAddress = l1_fee_token_address
        return self._l1FeeTokenAddress

    def get_l2_erc20_address(
        self, erc20_l1_address: str, l1_provider: Web3
    ) -> str:
        return self.l2Erc20Bridger.get_child_erc20_address(
            erc20_l1_address,
            l1_provider
        )

    def get_l3_erc20_address(
        self, erc20_l1_address: str, l1_provider: Web3, l2_provider: Web3
    ) -> str:
        l2_token = self.get_l2_erc20_address(erc20_l1_address, l1_provider)
        return self.l3Erc20Bridger.get_child_erc20_address(l2_token, l2_provider)

    def get_l1_l2_gateway_address(self, erc20_l1_address: str, l1_provider: Web3) -> str:
        return self.l2Erc20Bridger.get_parent_gateway_address(
            erc20_l1_address, l1_provider
        )

    def get_l2_l3_gateway_address(
        self, erc20_l1_address: str, l1_provider: Web3, l2_provider: Web3
    ) -> str:
        l2_token = self.get_l2_erc20_address(erc20_l1_address, l1_provider)
        return self.l3Erc20Bridger.get_parent_gateway_address(l2_token, l2_provider)

    def get_l1_token_contract(self, l1_token_addr: str, l1_provider: Web3):
        return load_contract(l1_provider, "ERC20", address=l1_token_addr)

    def get_l2_token_contract(self, l2_token_addr: str, l2_provider: Web3):
        return load_contract(l2_provider, "L2GatewayToken", address=l2_token_addr)

    def get_l3_token_contract(self, l3_token_addr: str, l3_provider: Web3):
        return load_contract(l3_provider, "L2GatewayToken", address=l3_token_addr)

    def l1_token_is_disabled(self, l1_token_address: str, l1_provider: Web3) -> bool:
        return self.l2Erc20Bridger.is_deposit_disabled(l1_token_address, l1_provider)

    def l2_token_is_disabled(self, l2_token_address: str, l2_provider: Web3) -> bool:
        return self.l3Erc20Bridger.is_deposit_disabled(l2_token_address, l2_provider)

    def l2_forwarder_address(
        self,
        owner: str,
        router_or_inbox: str,
        destination_address: str,
        l1_or_l2_provider: Web3
    ) -> str:
        chain_id = l1_or_l2_provider.eth.chain_id
        if chain_id == self.l1Network["chainId"]:
            predictor = self.teleporter.l1Teleporter
        elif chain_id == self.l2Network.chainId:
            predictor = self.teleporter.l2ForwarderFactory
        else:
            raise ArbSdkError(f"Unknown chain id: {chain_id}")

        predictor_contract = load_contract(
            l1_or_l2_provider,
            "IL2ForwarderPredictor",
            address=predictor
        )
        return predictor_contract.functions.l2ForwarderAddress(
            owner,
            router_or_inbox,
            destination_address
        ).call()

    def get_approve_token_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a transaction request to approve tokens for teleportation.
        """
        erc20_address = params["erc20L1Address"]
        amount = params.get("amount")
        if amount is None:
            amount = (1 << 256) - 1  # MaxUint256

        erc20_contract = create_contract_instance(
            # provider=None,
            contract_name="IERC20",
            # address=erc20_address
        )
        data = erc20_contract.encodeABI(
            fn_name="approve",
            args=[self.teleporter.l1Teleporter, amount]
        )

        return {
            "to": erc20_address,
            "data": data,
            "value": 0
        }

    def approve_token(self, params: Dict[str, Any]):
        l1_signer = params["l1Signer"]
        self._check_l1_network(l1_signer)

        if "txRequest" in params:
            approve_request = params["txRequest"]
        else:
            approve_request = self.get_approve_token_request(params)

        overrides = params.get("overrides", {})
        return l1_signer.send_transaction({**approve_request, **overrides})

    def get_approve_gas_token_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a tx request to approve the L3's fee token for teleportation.
        """
        amount = params.get("amount")
        fee_token_l1 = self.get_gas_token_on_l1(params["l1Provider"], params["l2Provider"])
        return self.get_approve_token_request({
            "erc20L1Address": fee_token_l1,
            "amount": amount
        })

    def approve_gas_token(self, params: Dict[str, Any]):
        l1_signer = params["l1Signer"]
        self._check_l1_network(l1_signer)

        if "txRequest" in params:
            approve_request = params["txRequest"]
        else:
            built = self.get_approve_gas_token_request({
                "l1Provider": l1_signer.provider,
                "l2Provider": params["l2Provider"],
                "amount": params.get("amount")
            })
            approve_request = built

        overrides = params.get("overrides", {})
        return l1_signer.send_transaction({**approve_request, **overrides})


    # ---------------------------------------------------------------------------
    # The bridging / deposit flow
    # ---------------------------------------------------------------------------

    def get_deposit_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Equivalent to getDepositRequest in TS
        """
        assert_arbitrum_network_has_token_bridge(self.l2Network)
        assert_arbitrum_network_has_token_bridge(self.l3Network)

        if "l1Provider" in params:
            l1_provider = params["l1Provider"]
        else:
            l1_signer = params["l1Signer"]
            l1_provider = l1_signer.provider

        self._check_l1_network(l1_provider)
        self._check_l2_network(params["l2Provider"])
        self._check_l3_network(params["l3Provider"])

        if "from" in params:
            from_addr = params["from"]
        else:
            from_addr = params["l1Signer"].get_address()

        if not self.l2GasTokenAddress:
            l1_fee_token = "0x0000000000000000000000000000000000000000"
        elif params.get("skipGasToken", False):
            l1_fee_token = self.skipL1GasTokenMagic
        else:
            l1_fee_token = self.get_gas_token_on_l1(l1_provider, params["l2Provider"])

        partial_teleport_params = {
            "l1Token": params["erc20L1Address"],
            "l3FeeTokenL1Addr": l1_fee_token,
            "l1l2Router": self.l2Network.tokenBridge.parentGatewayRouter,
            "l2l3RouterOrInbox":
                l1_fee_token
                and get_address(params["erc20L1Address"]) == get_address(l1_fee_token)
                and self.l3Network.ethBridge.inbox
                or self.l3Network.tokenBridge.parentGatewayRouter,
            "to": params.get("destinationAddress", from_addr),
            "amount": params["amount"],
        }

        retryable_overrides = params.get("retryableOverrides", {})

        filled = self._fill_partial_teleport_params(
            partial_teleport_params,
            retryable_overrides,
            l1_provider,
            params["l2Provider"],
            params["l3Provider"]
        )
        teleport_params = filled["teleportParams"]
        costs = filled["costs"]

        teleporter_contract = create_contract_instance(
            # l1_provider,
            "IL1Teleporter",
            # address=self.teleporter.l1Teleporter
        )
        data = teleporter_contract.encodeABI(
            fn_name="teleport",
            args=[teleport_params]
        )

        return {
            "txRequest": {
                "to": self.teleporter.l1Teleporter,
                "data": data,
                "value": costs["ethAmount"]
            },
            "gasTokenAmount": costs["feeTokenAmount"]
        }

    def deposit(self, params: Dict[str, Any]) -> ParentContractCallTransaction:
        self._check_l1_network(params["l1Signer"])

        if "txRequest" in params:
            deposit_request = params["txRequest"]
        else:
            dr = self.get_deposit_request(params)
            deposit_request = dr["txRequest"]

        overrides = params.get("overrides", {})
        tx = params["l1Signer"].sendTransaction({**deposit_request, **overrides})
        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx)

    def get_deposit_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._check_l1_network(params["l1Provider"])
        self._check_l2_network(params["l2Provider"])

        tx = self._get_tx_from_tx_ref(params, params["l1Provider"])
        tx_receipt = tx.wait()

        l1l2_messages = self._get_l1_to_l2_messages(tx_receipt, params["l2Provider"])

        l2_forwarder_params = self._decode_call_forwarder_calldata(
            l1l2_messages["l2ForwarderFactoryRetryable"]["messageData"]["data"]
        )

        l2_forwarder_address = self.l2_forwarder_address(
            l2_forwarder_params["owner"],
            l2_forwarder_params["routerOrInbox"],
            l2_forwarder_params["to"],
            params["l2Provider"]
        )

        teleport_params = self._decode_teleport_calldata(tx.data)

        return {
            "teleportParams": teleport_params,
            "l2ForwarderParams": l2_forwarder_params,
            "l2ForwarderAddress": l2_forwarder_address
        }

    def get_deposit_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._check_l1_network(params["l1Provider"])
        self._check_l2_network(params["l2Provider"])
        self._check_l3_network(params["l3Provider"])

        l1_tx_receipt = self._get_tx_receipt_from_tx_ref(params, params["l1Provider"])
        partial_result = self._get_l1_to_l2_messages(l1_tx_receipt, params["l2Provider"])

        factory_redeem = partial_result["l2ForwarderFactoryRetryable"].get_successful_redeem()

        if factory_redeem["status"] == ParentToChildMessageStatus.REDEEMED:
            child_ptx_receipt = ParentTransactionReceipt(factory_redeem["childTxReceipt"])
            l2l3_messages = child_ptx_receipt.getParentToChildMessages(params["l3Provider"])
            l2l3_message = l2l3_messages[0] if l2l3_messages else None
        else:
            l2l3_message = None

        l2_forwarder_factory_retryable_front_ran = False

        l1l2_token_bridge_status = partial_result["l1l2TokenBridgeRetryable"].status()
        if (
            l1l2_token_bridge_status == ParentToChildMessageStatus.REDEEMED
            and factory_redeem["status"] == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD
        ):
            decoded_factory_call = self._decode_call_forwarder_calldata(
                partial_result["l2ForwarderFactoryRetryable"]["messageData"]["data"]
            )
            forwarder_addr = self.l2_forwarder_address(
                decoded_factory_call["owner"],
                decoded_factory_call["routerOrInbox"],
                decoded_factory_call["to"],
                params["l2Provider"]
            )
            l2_token_contract = load_contract(params["l2Provider"], "IERC20", address=decoded_factory_call["l2Token"])
            balance = l2_token_contract.functions.balanceOf(forwarder_addr).call()
            if balance == 0:
                l2_forwarder_factory_retryable_front_ran = True

        if l2l3_message:
            completed = (l2l3_message.status()) == ParentToChildMessageStatus.REDEEMED
        else:
            completed = False

        ret = dict(partial_result)
        ret["l2l3TokenBridgeRetryable"] = l2l3_message
        ret["l2ForwarderFactoryRetryableFrontRan"] = l2_forwarder_factory_retryable_front_ran
        ret["completed"] = completed
        return ret

    def teleportation_type(self, partial_teleport_params: Dict[str, Any]) -> int:
        if partial_teleport_params["l3FeeTokenL1Addr"] == "0x0000000000000000000000000000000000000000":
            return TeleportationType.Standard
        elif get_address(partial_teleport_params["l1Token"]) == get_address(partial_teleport_params["l3FeeTokenL1Addr"]):
            return TeleportationType.OnlyGasToken
        else:
            return TeleportationType.NonGasTokenToCustomGas

    def _get_token_bridge_gas_estimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        parent_gateway = load_contract(
            params["parentProvider"],
            "L1GatewayRouter",  # or your gateway router name
            address=params["parentGatewayAddress"]
        )
        outbound_calldata = parent_gateway.functions.getOutboundCalldata(
            params["parentErc20Address"],
            params["from"],
            params["to"],
            params["amount"],
            "0x"
        ).call()

        estimates = ParentToChildMessageGasEstimator(params["childProvider"]).estimateAll(
            {
                "to": parent_gateway.functions.counterpartGateway().call(),
                "data": outbound_calldata,
                "from": parent_gateway.address,
                "l2CallValue": params["amount"] if params["isWeth"] else 0,
                "excessFeeRefundAddress": params["to"],
                "callValueRefundAddress": params["from"],
            },
            params["parentGasPrice"],
            params["parentProvider"]
        )

        return {
            "gasLimit": estimates["gasLimit"],
            "maxSubmissionFee": estimates["maxSubmissionCost"]
        }

    def _get_l1_l2_token_bridge_gas_estimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        assert_arbitrum_network_has_token_bridge(self.l2Network)
        parent_gateway_address = self.get_l1_l2_gateway_address(
            params["l1Token"], params["l1Provider"]
        )
        return self._get_token_bridge_gas_estimates({
            "parentProvider": params["l1Provider"],
            "childProvider": params["l2Provider"],
            "parentGasPrice": params["l1GasPrice"],
            "parentErc20Address": params["l1Token"],
            "parentGatewayAddress": parent_gateway_address,
            "from": self.teleporter.l1Teleporter,
            "to": params["l2ForwarderAddress"],
            "amount": params["amount"],
            "isWeth": (
                get_address(parent_gateway_address)
                == get_address(self.l2Network.tokenBridge["parentWethGateway"])
            ),
        })

    def _get_l1_l2_fee_token_bridge_gas_estimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        assert_arbitrum_network_has_token_bridge(self.l2Network)

        if params["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            return {"gasLimit": 0, "maxSubmissionFee": 0}

        parent_gateway_address = self.get_l1_l2_gateway_address(
            params["l3FeeTokenL1Addr"], params["l1Provider"]
        )
        return self._get_token_bridge_gas_estimates({
            "parentProvider": params["l1Provider"],
            "childProvider": params["l2Provider"],
            "parentGasPrice": params["l1GasPrice"],
            "parentErc20Address": params["l3FeeTokenL1Addr"],
            "parentGatewayAddress": parent_gateway_address,
            "from": self.teleporter.l1Teleporter,
            "to": params["l2ForwarderAddress"],
            "amount": params["feeTokenAmount"],
            "isWeth": (
                get_address(parent_gateway_address)
                == get_address(self.l2Network.tokenBridge["parentWethGateway"])
            ),
        })

    def _get_l2_forwarder_factory_gas_estimates(self, l1_gas_price: int, l1_provider: Web3) -> Dict[str, int]:
        inbox = load_contract(
            l1_provider,
            "IInbox",
            address=self.l2Network.ethBridge["inbox"]
        )
        size = self._l2_forwarder_factory_calldata_size()
        max_submission_fee = inbox.functions.calculateRetryableSubmissionFee(size, l1_gas_price).call()
        return {
            "gasLimit": self.l2ForwarderFactoryDefaultGasLimit,
            "maxSubmissionFee": max_submission_fee
        }

    def _get_l2_l3_bridge_gas_estimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        assert_arbitrum_network_has_token_bridge(self.l3Network)

        t_type = self.teleportation_type(params["partialTeleportParams"])
        if t_type == TeleportationType.NonGasTokenToCustomGas and \
           params["partialTeleportParams"]["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            return {"gasLimit": 0, "maxSubmissionFee": 0}
        elif t_type == TeleportationType.OnlyGasToken:
            partial = params["partialTeleportParams"]
            estimate = ParentToChildMessageGasEstimator(params["l3Provider"]).estimateAll(
                {
                    "to": partial["to"],
                    "data": "0x",
                    "from": params["l2ForwarderAddress"],
                    "l2CallValue": partial["amount"],
                    "excessFeeRefundAddress": partial["to"],
                    "callValueRefundAddress": partial["to"],
                },
                params["l2GasPrice"],
                params["l2Provider"]
            )
            return {
                "gasLimit": estimate["gasLimit"],
                "maxSubmissionFee": estimate["maxSubmissionCost"]
            }
        else:
            parent_gateway_address = self.get_l2_l3_gateway_address(
                params["partialTeleportParams"]["l1Token"],
                params["l1Provider"],
                params["l2Provider"]
            )
            l2_token_addr = self.get_l2_erc20_address(
                params["partialTeleportParams"]["l1Token"],
                params["l1Provider"]
            )
            is_weth = (
                get_address(parent_gateway_address)
                == get_address(self.l3Network.tokenBridge["parentWethGateway"])
            )
            return self._get_token_bridge_gas_estimates({
                "parentProvider": params["l2Provider"],
                "childProvider": params["l3Provider"],
                "parentGasPrice": params["l2GasPrice"],
                "parentErc20Address": l2_token_addr,
                "parentGatewayAddress": parent_gateway_address,
                "from": params["l2ForwarderAddress"],
                "to": params["partialTeleportParams"]["to"],
                "amount": params["partialTeleportParams"]["amount"],
                "isWeth": is_weth
            })

    def _fill_partial_teleport_params(
        self,
        partial_teleport_params: Dict[str, Any],
        retryable_overrides: Dict[str, Any],
        l1_provider: Web3,
        l2_provider: Web3,
        l3_provider: Web3
    ) -> Dict[str, Any]:

        def get_retryable_gas_values_with_overrides(
            overrides: Optional[Dict[str, Any]],
            get_estimates
        ) -> Dict[str, int]:
            if overrides and \
               "gasLimit" in overrides and "maxSubmissionFee" in overrides and \
               "base" in overrides["gasLimit"] and "base" in overrides["maxSubmissionFee"]:
                base_gas_limit = overrides["gasLimit"]["base"]
                base_max_submission_fee = overrides["maxSubmissionFee"]["base"]
            else:
                calc = get_estimates()
                base_gas_limit = overrides.get("gasLimit", {}).get("base", calc["gasLimit"]) if overrides else calc["gasLimit"]
                base_max_submission_fee = overrides.get("maxSubmissionFee", {}).get("base", calc["maxSubmissionFee"]) if overrides else calc["maxSubmissionFee"]

            gas_limit_increase = overrides.get("gasLimit", {}).get("percentIncrease", self.defaultGasLimitPercentIncrease) if overrides else self.defaultGasLimitPercentIncrease
            sub_fee_increase = overrides.get("maxSubmissionFee", {}).get("percentIncrease", 0) if overrides else 0

            gas_limit_adjusted = self._percent_increase(base_gas_limit, gas_limit_increase)
            sub_fee_adjusted = self._percent_increase(base_max_submission_fee, sub_fee_increase)

            min_gas_limit = overrides.get("gasLimit", {}).get("min", 0) if overrides else 0
            if gas_limit_adjusted < min_gas_limit:
                gas_limit_adjusted = min_gas_limit

            return {
                "gasLimit": gas_limit_adjusted,
                "maxSubmissionFee": sub_fee_adjusted
            }

        def apply_gas_percent_increase(
            override_dict: Dict[str, Any],
            get_estimate
        ) -> int:
            base_val = override_dict.get("base") if override_dict else None
            if not base_val:
                # call get_estimate
                val = get_estimate()
                if callable(val):
                    val = val
                base_val = val

            inc = override_dict.get("percentIncrease", self.defaultGasPricePercentIncrease) if override_dict else self.defaultGasPricePercentIncrease
            return self._percent_increase(base_val, inc)

        l1_gas_price = apply_gas_percent_increase(retryable_overrides.get("l1GasPrice", {}), lambda: l1_provider.eth.gas_price)
        l2_gas_price = apply_gas_percent_increase(retryable_overrides.get("l2GasPrice", {}), lambda: l2_provider.eth.gas_price)

        if partial_teleport_params["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            l3_gas_price = 0
        else:
            l3_gas_price = apply_gas_percent_increase(retryable_overrides.get("l3GasPrice", {}), lambda: l3_provider.eth.gas_price)

        fake_random_l2_forwarder = "0x" + os.urandom(20).hex()

        l1l2_token_bridge = get_retryable_gas_values_with_overrides(
            retryable_overrides.get("l1l2TokenBridgeRetryableGas"),
            lambda: self._get_l1_l2_token_bridge_gas_estimates({
                "l1Token": partial_teleport_params["l1Token"],
                "amount": partial_teleport_params["amount"],
                "l1GasPrice": l1_gas_price,
                "l2ForwarderAddress": fake_random_l2_forwarder,
                "l1Provider": l1_provider,
                "l2Provider": l2_provider
            })
        )

        l2_forwarder_factory = get_retryable_gas_values_with_overrides(
            retryable_overrides.get("l2ForwarderFactoryRetryableGas"),
            lambda: self._get_l2_forwarder_factory_gas_estimates(l1_gas_price, l1_provider)
        )

        l2l3_token_bridge = get_retryable_gas_values_with_overrides(
            retryable_overrides.get("l2l3TokenBridgeRetryableGas"),
            lambda: self._get_l2_l3_bridge_gas_estimates({
                "partialTeleportParams": partial_teleport_params,
                "l2GasPrice": l2_gas_price,
                "l1Provider": l1_provider,
                "l2Provider": l2_provider,
                "l3Provider": l3_provider,
                "l2ForwarderAddress": fake_random_l2_forwarder
            })
        )

        from_type = self.teleportation_type(partial_teleport_params)
        if from_type == TeleportationType.NonGasTokenToCustomGas:
            fee_gas = get_retryable_gas_values_with_overrides(
                retryable_overrides.get("l1l2GasTokenBridgeRetryableGas"),
                lambda: self._get_l1_l2_fee_token_bridge_gas_estimates({
                    "l1GasPrice": l1_gas_price,
                    "feeTokenAmount": (l2l3_token_bridge["gasLimit"] * l3_gas_price)
                                      + l2l3_token_bridge["maxSubmissionFee"],
                    "l3FeeTokenL1Addr": partial_teleport_params["l3FeeTokenL1Addr"],
                    "l2ForwarderAddress": fake_random_l2_forwarder,
                    "l1Provider": l1_provider,
                    "l2Provider": l2_provider
                })
            )
            l1l2_fee_token_bridge = {
                "gasLimit": fee_gas["gasLimit"],
                "maxSubmissionFee": fee_gas["maxSubmissionFee"]
            }
        else:
            l1l2_fee_token_bridge = {"gasLimit": 0, "maxSubmissionFee": 0}

        gas_params = {
            "l2GasPriceBid": l2_gas_price,
            "l3GasPriceBid": l3_gas_price,
            "l1l2TokenBridgeGasLimit": l1l2_token_bridge["gasLimit"],
            "l1l2FeeTokenBridgeGasLimit": l1l2_fee_token_bridge["gasLimit"],
            "l2l3TokenBridgeGasLimit": l2l3_token_bridge["gasLimit"],
            "l2ForwarderFactoryGasLimit": l2_forwarder_factory["gasLimit"],
            "l2ForwarderFactoryMaxSubmissionCost": l2_forwarder_factory["maxSubmissionFee"],
            "l1l2TokenBridgeMaxSubmissionCost": l1l2_token_bridge["maxSubmissionFee"],
            "l1l2FeeTokenBridgeMaxSubmissionCost": l1l2_fee_token_bridge["maxSubmissionFee"],
            "l2l3TokenBridgeMaxSubmissionCost": l2l3_token_bridge["maxSubmissionFee"],
        }

        teleport_params = dict(partial_teleport_params)
        teleport_params["gasParams"] = gas_params

        teleporter_contract = load_contract(
            l1_provider, "IL1Teleporter", address=self.teleporter.l1Teleporter
        )
        costs = teleporter_contract.functions.determineTypeAndFees(teleport_params).call()

        return {"teleportParams": teleport_params, "costs": costs}

    def _l2_forwarder_factory_calldata_size(self) -> int:
        struct_params = {
            "owner": "0x0000000000000000000000000000000000000000",
            "l2Token": "0x0000000000000000000000000000000000000000",
            "l3FeeTokenL2Addr": "0x0000000000000000000000000000000000000000",
            "routerOrInbox": "0x0000000000000000000000000000000000000000",
            "to": "0x0000000000000000000000000000000000000000",
            "gasLimit": 0,
            "gasPriceBid": 0,
            "maxSubmissionCost": 0,
        }
        forwarder_factory = create_contract_instance(
            # provider=None,
            contract_name="IL2ForwarderFactory",
            # address="0x0000000000000000000000000000000000000000"
        )
        dummy_calldata = forwarder_factory.encodeABI(
            fn_name="callForwarder",
            args=[struct_params]
        )
        hex_str = dummy_calldata[2:] if dummy_calldata.startswith("0x") else dummy_calldata
        total_bytes = len(hex_str) // 2
        return total_bytes - 4

    def _decode_teleport_calldata(self, data: str) -> Dict[str, Any]:
        teleporter_iface = create_contract_instance(
            # provider=None,
            contract_name="IL1Teleporter",
            # address="0x0000000000000000000000000000000000000000"
        )
        decoded = teleporter_iface.decode_function_input("teleport", data)
        if not decoded or decoded[0] != "teleport":
            raise ArbSdkError("not a teleport tx")
        return decoded[1]

    def _decode_call_forwarder_calldata(self, data: str) -> Dict[str, Any]:
        forwarder_factory = create_contract_instance(
            # provider=None,
            contract_name="IL2ForwarderFactory",
            # address="0x0000000000000000000000000000000000000000"
        )
        decoded = forwarder_factory.decode_function_input("callForwarder", data)
        if not decoded or decoded[0] != "callForwarder":
            raise ArbSdkError("not callForwarder data")
        return decoded[1]

    def _get_l1_to_l2_messages(
        self,
        l1_tx_receipt: ParentContractCallTransactionReceipt,
        l2_provider: Web3
    ) -> Dict[str, Optional[ParentToChildMessageReader]]:
        l1l2_messages: List[ParentToChildMessageReader] = l1_tx_receipt.getParentToChildMessages(l2_provider)

        if len(l1l2_messages) == 2:
            return {
                "l1l2TokenBridgeRetryable": l1l2_messages[0],
                "l2ForwarderFactoryRetryable": l1l2_messages[1],
                "l1l2GasTokenBridgeRetryable": None
            }
        else:
            return {
                "l1l2GasTokenBridgeRetryable": l1l2_messages[0],
                "l1l2TokenBridgeRetryable": l1l2_messages[1],
                "l2ForwarderFactoryRetryable": l1l2_messages[2],
            }


# ------------------------------------------------------------------------------------
# EthL1L3Bridger
# ------------------------------------------------------------------------------------

class EthL1L3Bridger(BaseL1L3Bridger):
    def __init__(self, l3_network: ArbitrumNetwork):
        super().__init__(l3_network)
        if l3_network.nativeToken and l3_network.nativeToken != "0x0000000000000000000000000000000000000000":
            raise ArbSdkError(
                f"L3 network {l3_network.name} uses a custom fee token"
            )

    def get_deposit_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if "l1Provider" in params:
            l1_provider = params["l1Provider"]
        else:
            l1_signer = params["l1Signer"]
            l1_provider = l1_signer.provider

        self._check_l1_network(l1_provider)
        self._check_l2_network(params["l2Provider"])
        self._check_l3_network(params["l3Provider"])

        if "from" in params:
            from_addr = params["from"]
        else:
            from_addr = params["l1Signer"].get_address()

        l3_destination_address = params.get("destinationAddress", from_addr)
        l2_refund_address = params.get("l2RefundAddress", from_addr)

        # Construct the L3 ticket (inner) then wrap an L2 ticket
        # You'd presumably call something akin to:
        #   l3TicketRequest = ParentToChildMessageCreator.get_ticket_creation_request(...)
        # For brevity, we assume a placeholder method `_create_retryable_ticket_request(...)`
        l3_ticket_request = ParentToChildMessageCreator.get_ticket_creation_request(
            {
                "to": l3_destination_address,
                "data": "0x",
                "from": get_address(from_addr).lower(),  # or any alias logic
                "l2CallValue": params["amount"],
                "excessFeeRefundAddress": l3_destination_address,
                "callValueRefundAddress": l3_destination_address,
            },
            params["l2Provider"],
            params["l3Provider"],
            params.get("l3TicketGasOverrides")
        )

        l2_ticket_request = ParentToChildMessageCreator.get_ticket_creation_request(
            {
                "from": from_addr,
                "to": l3_ticket_request["txRequest"]["to"],
                "l2CallValue": l3_ticket_request["txRequest"]["value"],
                "data": l3_ticket_request["txRequest"]["data"],
                "excessFeeRefundAddress": l2_refund_address,
                "callValueRefundAddress": l2_refund_address,
            },
            l1_provider,
            params["l2Provider"],
            params.get("l2TicketGasOverrides")
        )

        return l2_ticket_request

    def deposit(self, params: Dict[str, Any]) -> ParentContractCallTransaction:
        self._check_l1_network(params["l1Signer"])

        if "txRequest" in params:
            deposit_request = params["txRequest"]
        else:
            dr = self.get_deposit_request(params)
            deposit_request = dr["txRequest"]

        overrides = params.get("overrides", {})
        tx = params["l1Signer"].sendTransaction({**deposit_request, **overrides})
        return ParentTransactionReceipt.monkey_patch_contract_call_wait(tx)

    def get_deposit_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._check_l1_network(params["l1Provider"])

        tx = self._get_tx_from_tx_ref(params, params["l1Provider"])

        l1l2_ticket_data = dict(self._decode_create_retryable_ticket(tx.data))
        l1l2_ticket_data["l1Value"] = tx.value

        l2l3_ticket_data = dict(self._decode_create_retryable_ticket(l1l2_ticket_data["data"]))
        l2l3_ticket_data["l1Value"] = l1l2_ticket_data["l2CallValue"]

        return {
            "l1l2TicketData": l1l2_ticket_data,
            "l2l3TicketData": l2l3_ticket_data
        }

    def get_deposit_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._check_l1_network(params["l1Provider"])
        self._check_l2_network(params["l2Provider"])
        self._check_l3_network(params["l3Provider"])

        l1_tx_receipt = self._get_tx_receipt_from_tx_ref(params, params["l1Provider"])
        all_messages = l1_tx_receipt.getParentToChildMessages(params["l2Provider"])
        if not all_messages:
            return {
                "l2Retryable": None,
                "l3Retryable": None,
                "completed": False
            }

        l1l2_message = all_messages[0]
        l1l2_redeem = l1l2_message.get_successful_redeem()
        if l1l2_redeem["status"] != ParentToChildMessageStatus.REDEEMED:
            return {
                "l2Retryable": l1l2_message,
                "l3Retryable": None,
                "completed": False
            }

        child_tx_receipt = ParentEthDepositTransactionReceipt(l1l2_redeem["childTxReceipt"])
        l2l3_msgs = child_tx_receipt.getParentToChildMessages(params["l3Provider"])
        if not l2l3_msgs:
            raise ArbSdkError("L2 to L3 message not found")

        l2l3_message = l2l3_msgs[0]
        completed = (l2l3_message.status()) == ParentToChildMessageStatus.REDEEMED
        return {
            "l2Retryable": l1l2_message,
            "l3Retryable": l2l3_message,
            "completed": completed
        }

    def _decode_create_retryable_ticket(self, data: str) -> Dict[str, Any]:
        inbox_iface = create_contract_instance(
            # provider=None,
            contract_name="IInbox",
            # address="0x0000000000000000000000000000000000000000"
        )
        decoded = inbox_iface.decode_function_input("createRetryableTicket", data)
        if not decoded or decoded[0] != "createRetryableTicket":
            raise ArbSdkError("not createRetryableTicket data")
        args = decoded[1]
        return {
            "destAddress": args[0],
            "l2CallValue": args[1],
            "maxSubmissionFee": args[2],
            "excessFeeRefundAddress": args[3],
            "callValueRefundAddress": args[4],
            "gasLimit": args[5],
            "maxFeePerGas": args[6],
            "data": args[7],
        }
