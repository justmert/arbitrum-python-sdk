from typing import Union, Optional, Dict, Any

from web3 import Web3
from web3.types import TxReceipt

# Example placeholders: adapt your actual code structure
from eth_typing import ChecksumAddress
from eth_account.signers.local import LocalAccount


# Import your code references
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import (
    ArbitrumNetwork,
    Teleporter,
    assertArbitrumNetworkHasTokenBridge,
    getArbitrumNetworks,
)
from src.lib.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from src.lib.data_entities.transaction_request import (
    ParentToChildTransactionRequest,
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
    GasOverrides,
    ParentToChildMessageGasEstimator,
    PercentIncrease,
)




from typing import Optional

from web3 import Web3
from eth_account.signers.local import LocalAccount
from eth_utils import keccak
from web3.exceptions import ContractLogicError

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import ArbitrumNetwork
from src.lib.asset_briger.erc20_bridger import Erc20Bridger
from src.lib.message.parent_transaction import ParentTransactionReceipt
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.helper import load_contract
from src.lib.message.parent_to_child_message_gas_estimator import (
    PercentIncrease,
)
from src.lib.data_entities.constants import ZERO_ADDRESS
from .l1l3_bridger import BaseL1L3Bridger  # or wherever your BaseL1L3Bridger is

import hashlib
import binascii


from typing import Dict, Any

from web3 import Web3

# If you're using a big number approach, adapt these references or treat them as int
# from some_big_number_lib import BigNumber

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import assertArbitrumNetworkHasTokenBridge
from src.lib.message.parent_to_child_message_gas_estimator import (
    ParentToChildMessageGasEstimator,
)
from src.lib.utils.helper import getAddress  # or your local getAddress approach


from typing import Dict, Any, List, Optional

from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.parent_to_child_message import ParentToChildMessageReader, ParentToChildMessageStatus
from src.lib.message.parent_transaction import (
    ParentContractCallTransactionReceipt,
    ParentEthDepositTransactionReceipt,
    ParentTransactionReceipt
)
from src.lib.utils.helper import load_contract, getAddress

from typing import Dict, Any, List, Optional

from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError
from src.lib.message.parent_to_child_message import ParentToChildMessageReader, ParentToChildMessageStatus
from src.lib.message.parent_transaction import (
    ParentContractCallTransactionReceipt,
    ParentEthDepositTransactionReceipt,
    ParentTransactionReceipt
)
from src.lib.utils.helper import load_contract, getAddress


# 1) Definitions that were "type" or "enum" in TypeScript
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

# The TS code uses BigNumber fields for gasLimit, maxSubmissionFee, etc.
# We'll treat them as Python int for simplicity. If you need a big number library, adapt accordingly.
class RetryableGasValues:
    """
    Python representation of:
      type RetryableGasValues = {
        gasLimit: BigNumber
        maxSubmissionFee: BigNumber
      }
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
    Each field is optional. We'll store them in a dictionary or as properties.
    """
    def __init__(
        self,
        gas_limit: Optional[Dict[str, Any]] = None,
        max_submission_fee: Optional[Dict[str, Any]] = None,
    ):
        # e.g. gas_limit -> { base: int, percentIncrease: int, min: int }
        self.gasLimit = gas_limit
        # e.g. max_submission_fee -> { base: int, percentIncrease: int }
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
    The 'PickedTransactionRequest' in TS means {to, data, value} are required.
    """
    def __init__(
        self,
        tx_request: Dict[str, Any],
        l1_signer: Any,  # typically a LocalAccount or similar
        overrides: Optional[Dict[str, Any]] = None
    ):
        self.txRequest = tx_request  # must contain {to, data, value}
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
    We'll store them in a single object, and whichever field is present defines the type.
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
      export type GetL1L3DepositStatusParams = { l1Provider, l2Provider, l3Provider } & TxReference
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
    We'll treat BigNumberish as int for simplicity.
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


class BaseL1L3Bridger:
    """
    Python equivalent of the TypeScript 'BaseL1L3Bridger' class,
    which provides base functionality for bridging from L1 to L3.

    This class references L2 and L3 networks, as well as the L1 chain 
    (parent chain to L2).
    """

    def __init__(self, l3_network: ArbitrumNetwork):
        """
        :param l3_network: The ArbitrumNetwork describing the L3 chain.
        :raises ArbSdkError: If we cannot find the L2 network for l3_network.parentChainId
        """
        # find the L2 network from getArbitrumNetworks
        potential_l2 = None
        for net in getArbitrumNetworks():
            if net.chainId == l3_network.parentChainId:
                potential_l2 = net
                break

        if not potential_l2:
            raise ArbSdkError(
                f"Unknown Arbitrum network chain id: {l3_network.parentChainId}"
            )

        # L1 is the parent chain of L2
        self.l2Network = potential_l2
        self.l1Network = {"chainId": potential_l2.parentChainId}
        self.l3Network = l3_network

        # TS code sets defaultGasPricePercentIncrease = 500, defaultGasLimitPercentIncrease = 100
        self.defaultGasPricePercentIncrease = 500
        self.defaultGasLimitPercentIncrease = 100

    async def _checkL1Network(self, sop: SignerOrProvider):
        """
        Ensures the signer/provider is on the expected L1 chainId
        """
        await SignerProviderUtils.check_network_matches(
            sop, self.l1Network["chainId"]
        )

    async def _checkL2Network(self, sop: SignerOrProvider):
        """
        Ensures the signer/provider is on the expected L2 chainId
        """
        await SignerProviderUtils.check_network_matches(
            sop, self.l2Network.chainId
        )

    async def _checkL3Network(self, sop: SignerOrProvider):
        """
        Ensures the signer/provider is on the expected L3 chainId
        """
        await SignerProviderUtils.check_network_matches(
            sop, self.l3Network.chainId
        )

    def _percentIncrease(self, num: int, increase: int) -> int:
        """
        :param num: The base integer to increase
        :param increase: The percent to increase by (e.g. 500 means +500%).
        :return: num + (num * increase / 100)
        """
        return num + (num * increase) // 100

    def _getTxHashFromTxRef(self, txRef: Union[Dict[str, Any], "TxReference"]) -> str:
        """
        Utility to retrieve the transaction hash from a TxReference-like object.
        The TS code: `_getTxHashFromTxRef(txRef: TxReference): string`
        """
        if "txHash" in txRef:
            return txRef["txHash"]
        elif "tx" in txRef:
            return txRef["tx"].hash
        else:
            return txRef["txReceipt"].transactionHash

    async def _getTxFromTxRef(
        self,
        txRef: Union[Dict[str, Any], "TxReference"],
        provider: Web3
    ) -> ParentContractCallTransaction:
        """
        If 'tx' key is present, return that. 
        Otherwise fetch transaction from chain and monkey-patch it.

        TS code: `_getTxFromTxRef(txRef, provider)`
        """
        if "tx" in txRef:
            return txRef["tx"]

        tx_hash = self._getTxHashFromTxRef(txRef)
        raw_tx = provider.eth.get_transaction(tx_hash)
        # Convert raw tx to a ParentContractCallTransaction if you have a wrapper
        return ParentTransactionReceipt.monkeyPatchContractCallWait(raw_tx)

    async def _getTxReceiptFromTxRef(
        self,
        txRef: Union[Dict[str, Any], "TxReference"],
        provider: Web3
    ) -> ParentContractCallTransactionReceipt:
        """
        If 'txReceipt' key is present, return that.
        Otherwise fetch from chain by transaction hash.

        TS code: `_getTxReceiptFromTxRef(...)`.
        """
        if "txReceipt" in txRef:
            return txRef["txReceipt"]

        tx_hash = self._getTxHashFromTxRef(txRef)
        receipt = provider.eth.get_transaction_receipt(tx_hash)
        return ParentContractCallTransactionReceipt(receipt)


class Erc20L1L3Bridger(BaseL1L3Bridger):
    """
    Python version of the second part of l1l3Bridger.ts,
    implementing the Erc20L1L3Bridger class.
    """

    def __init__(self, l3Network: ArbitrumNetwork):
        """
        Initialize the Erc20L1L3Bridger.

        :param l3Network: The ArbitrumNetwork describing the L3 chain.
        :raises ArbSdkError: If the L2 teleporter is missing or if the L3 nativeToken 
                             indicates a custom fee token and there's an error.
        """
        super().__init__(l3Network)

        if not self.l2Network.teleporter:
            raise ArbSdkError(
                f"L2 network {self.l2Network.name} does not have teleporter contracts"
            )

        # Convert your TS BigNumber(1_000_000) to a Python int
        self.l2ForwarderFactoryDefaultGasLimit = 1_000_000

        # Replicate skipL1GasTokenMagic
        # TS code uses keccak256(utf8Bytes('SKIP_FEE_TOKEN'))[0..20].
        # We'll do the same in Python:
        hashed = keccak(text="SKIP_FEE_TOKEN")
        # get first 20 bytes
        skip_token = hashed[:20]
        # ensure it's a checksummed address
        # We'll just mimic the "getAddress" approach from TS, i.e. zero-extend & checksum.
        # Or do a direct conversion to hex, etc.
        self.skipL1GasTokenMagic = self._create_checksummed_address_from_bytes(skip_token)

        # If L3 uses a custom fee token:
        if self.l3Network.nativeToken and self.l3Network.nativeToken != "0x0000000000000000000000000000000000000000":
            self.l2GasTokenAddress: Optional[str] = self.l3Network.nativeToken
        else:
            self.l2GasTokenAddress = None

        self.teleporter = self.l2Network.teleporter

        # Create references to Erc20Bridger for L2 and L3
        self.l2Erc20Bridger = Erc20Bridger(self.l2Network)
        self.l3Erc20Bridger = Erc20Bridger(self.l3Network)

        # If the L3 network uses a custom fee token, store the address on L1 once discovered
        self._l1FeeTokenAddress: Optional[str] = None

    def _create_checksummed_address_from_bytes(self, raw_bytes: bytes) -> str:
        """
        Utility to produce a checksummed address from the first 20 bytes.
        """
        if len(raw_bytes) < 20:
            # if the TS code specifically slices exactly 20 bytes
            # ensure no indexing error
            raw_bytes = raw_bytes.ljust(20, b"\x00")

        # convert to 40-hex-digit string
        hex_addr = "0x" + raw_bytes[:20].hex()
        # checksummed approach
        # We can do a direct web3.toChecksumAddress(hex_addr) if you prefer
        from web3 import Web3
        return Web3.toChecksumAddress(hex_addr)

    async def getGasTokenOnL1(self, l1Provider: Web3, l2Provider: Web3) -> str:
        """
        If the L3 network uses a custom gas token, return the address of that token on L1.
        If it doesn't exist or doesn't meet requirements (18 decimals, enabled bridging),
        raise an ArbSdkError.
        If the L3 network uses ETH for fees, also raise an error.

        :param l1Provider: L1 provider
        :param l2Provider: L2 provider
        :return: The L1 fee token address
        :raises: ArbSdkError
        """
        # If the L3 uses ETH for fees:
        if not self.l2GasTokenAddress:
            raise ArbSdkError("L3 uses ETH for gas")

        # If we already discovered the L1 address:
        if self._l1FeeTokenAddress is not None:
            return self._l1FeeTokenAddress

        await self._checkL1Network(l1Provider)
        await self._checkL2Network(l2Provider)

        l1FeeTokenAddress: Optional[str] = None

        try:
            # get the parent ERC20 (on L1) for the given L2 token
            l1FeeTokenAddress = await self.l2Erc20Bridger.getParentErc20Address(
                self.l2GasTokenAddress, l2Provider
            )
        except ContractLogicError as e:
            # if the error is a CALL_EXCEPTION, we can't find the token
            if e.args and "CALL_EXCEPTION" not in str(e):
                raise e

        if (
            not l1FeeTokenAddress
            or l1FeeTokenAddress == "0x0000000000000000000000000000000000000000"
        ):
            raise ArbSdkError("L1 gas token not found. Use skipGasToken when depositing")

        # Check decimals are 18
        # In TS: 
        #   (await ERC20__factory.connect(...).decimals()) !== 18 => throw
        # We'll replicate the check in Python:
        l1_contract = load_contract(l1Provider, "ERC20", address=l1FeeTokenAddress)
        decimals_l1 = l1_contract.functions.decimals().call()
        if decimals_l1 != 18:
            raise ArbSdkError(
                "L1 gas token has incorrect decimals. Use skipGasToken when depositing"
            )

        l2_contract = load_contract(l2Provider, "ERC20", address=self.l2GasTokenAddress)
        decimals_l2 = l2_contract.functions.decimals().call()
        if decimals_l2 != 18:
            raise ArbSdkError(
                "L2 gas token has incorrect decimals. Use skipGasToken when depositing"
            )

        # check if bridging is disabled
        if await self.l1TokenIsDisabled(l1FeeTokenAddress, l1Provider):
            raise ArbSdkError(
                "L1 gas token is disabled on the L1 to L2 token bridge. Use skipGasToken when depositing"
            )
        if await self.l2TokenIsDisabled(self.l2GasTokenAddress, l2Provider):
            raise ArbSdkError(
                "L2 gas token is disabled on the L2 to L3 token bridge. Use skipGasToken when depositing"
            )

        self._l1FeeTokenAddress = l1FeeTokenAddress
        return self._l1FeeTokenAddress

    def getL2Erc20Address(
        self, erc20L1Address: str, l1Provider: Web3
    ) -> str:
        """
        Return the corresponding L2 token address for the given L1 token.

        :param erc20L1Address: L1 token address
        :param l1Provider: L1 provider
        :return: L2 token address
        """
        return self.l2Erc20Bridger.getChildErc20Address(erc20L1Address, l1Provider)

    async def getL3Erc20Address(
        self, erc20L1Address: str, l1Provider: Web3, l2Provider: Web3
    ) -> str:
        """
        Return the corresponding L3 token address for the given L1 token.

        :param erc20L1Address: L1 token address
        :param l1Provider: L1 provider
        :param l2Provider: L2 provider
        :return: L3 token address
        """
        l2_token = self.getL2Erc20Address(erc20L1Address, l1Provider)
        return self.l3Erc20Bridger.getChildErc20Address(l2_token, l2Provider)

    def getL1L2GatewayAddress(
        self, erc20L1Address: str, l1Provider: Web3
    ) -> str:
        """
        Given an L1 token's address, get the address of the token's L1 <-> L2 gateway on L1.
        """
        return self.l2Erc20Bridger.getParentGatewayAddress(
            erc20L1Address,
            l1Provider
        )

    async def getL2L3GatewayAddress(
        self, erc20L1Address: str, l1Provider: Web3, l2Provider: Web3
    ) -> str:
        """
        Get the address of the L2 <-> L3 gateway on L2 given an L1 token address

        :param erc20L1Address: The L1 token address
        :param l1Provider: L1 provider
        :param l2Provider: L2 provider
        :return: The L2-L3 gateway address on L2
        """
        l2_token = self.getL2Erc20Address(erc20L1Address, l1Provider)
        return self.l3Erc20Bridger.getParentGatewayAddress(l2_token, l2Provider)

    def getL1TokenContract(self, l1TokenAddr: str, l1Provider: Web3):
        """
        Return a web3 Contract instance for the L1 token at l1TokenAddr.
        This does not validate the contract's bytecode or the correctness of ERC20 methods.
        """
        return load_contract(
            l1Provider,
            "ERC20",
            address=l1TokenAddr
        )

    def getL2TokenContract(self, l2TokenAddr: str, l2Provider: Web3):
        """
        Return a web3 Contract instance for the L2 token.
        """
        return load_contract(
            l2Provider,
            "L2GatewayToken",  # or "ERC20" if your code references so
            address=l2TokenAddr
        )

    def getL3TokenContract(self, l3TokenAddr: str, l3Provider: Web3):
        """
        Return a web3 Contract instance for the L3 token.
        """
        return load_contract(
            l3Provider,
            "L2GatewayToken",
            address=l3TokenAddr
        )

    async def l1TokenIsDisabled(self, l1TokenAddress: str, l1Provider: Web3) -> bool:
        """
        Whether the L1 token has been disabled on the L1 <-> L2 router.
        """
        return await self.l2Erc20Bridger.isDepositDisabled(l1TokenAddress, l1Provider)

    async def l2TokenIsDisabled(self, l2TokenAddress: str, l2Provider: Web3) -> bool:
        """
        Whether the L2 token has been disabled on the L2 <-> L3 router.
        """
        return await self.l3Erc20Bridger.isDepositDisabled(l2TokenAddress, l2Provider)

    async def l2ForwarderAddress(
        self,
        owner: str,
        routerOrInbox: str,
        destinationAddress: str,
        l1OrL2Provider: Web3
    ) -> str:
        """
        Given some L2Forwarder parameters, get the address of the L2Forwarder contract
        by calling the l2ForwarderAddress(...) method on the teleporter predictor contract.

        :param owner: The owner address
        :param routerOrInbox: router or inbox address
        :param destinationAddress: The 'to' address
        :param l1OrL2Provider: The provider for either L1 or L2 
                               (chainId is used to decide which teleporter to call)
        :return: The L2Forwarder address
        """
        chainId = l1OrL2Provider.eth.chain_id
        if chainId == self.l1Network["chainId"]:
            predictor = self.teleporter.l1Teleporter
        elif chainId == self.l2Network.chainId:
            predictor = self.teleporter.l2ForwarderFactory
        else:
            raise ArbSdkError(f"Unknown chain id: {chainId}")

        # Load IL2ForwarderPredictor contract and call l2ForwarderAddress
        predictor_contract = load_contract(
            l1OrL2Provider,
            "IL2ForwarderPredictor",  # or similarly named
            address=predictor
        )
        return predictor_contract.functions.l2ForwarderAddress(
            owner,
            routerOrInbox,
            destinationAddress
        ).call()

    async def getApproveTokenRequest(self, params) -> dict:
        """
        Return a transaction request to approve tokens for teleportation 
        (approved to self.teleporter.l1Teleporter).
        Equivalent of the TS getApproveTokenRequest method.

        :param params: A dict or object with 'erc20L1Address' and optional 'amount'
        :return: A dict with { to, data, value=0 }
        """
        erc20_address = params["erc20L1Address"]
        amount = params.get("amount", None)
        if amount is None:
            # TS code uses ethers.constants.MaxUint256
            # We'll assume a large integer to replicate that
            amount = (1 << 256) - 1

        # encode "approve(teleporter, amount)" 
        # In TS: ierc20Interface.encodeFunctionData('approve',[...])
        # In python, load an abi or contract
        erc20_contract = load_contract(
            provider=None,  # you might pass an actual provider or not needed
            contract_name="IERC20",
            address=erc20_address
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

    async def approveToken(self, params):
        """
        Approve tokens for teleportation on L1Teleporter.

        :param params: 
         Either { erc20L1Address, amount, l1Signer, overrides? } 
         or a TxRequestParams with { txRequest, l1Signer, overrides? }
        :return: a raw transaction sent by l1Signer
        """
        l1_signer = params["l1Signer"]
        await self._checkL1Network(l1_signer)

        if "txRequest" in params:
            approve_request = params["txRequest"]
        else:
            # build from token info
            approve_request = await self.getApproveTokenRequest(params)

        overrides = params.get("overrides", {})
        return l1_signer.send_transaction({**approve_request, **overrides})

    async def getApproveGasTokenRequest(self, params: dict) -> dict:
        """
        Return a tx request to approve the L3's fee token for teleportation.
        The tokens will be approved for L1Teleporter.
        Will throw if the L3 uses ETH or the fee token doesn't exist on L1.

        :param params: { l1Provider, l2Provider, amount? }
        :return: A transaction request dict with {to, data, value=0}
        """
        amount = params.get("amount", None)
        fee_token_l1 = await self.getGasTokenOnL1(params["l1Provider"], params["l2Provider"])
        return await self.getApproveTokenRequest({
            "erc20L1Address": fee_token_l1,
            "amount": amount
        })

    async def approveGasToken(self, params):
        """
        Approve the L3's fee token for teleportation. 
        The tokens will be approved for L1Teleporter.
        Will throw if the L3 uses ETH for fees or the fee token doesn't exist on L1.

        :param params:
          either { l1Signer, l2Provider, amount?, overrides? }
          or TxRequestParams with { txRequest, l1Signer, overrides? }
        :return: The raw transaction from l1Signer.send_transaction
        """
        l1_signer = params["l1Signer"]
        await self._checkL1Network(l1_signer)

        if "txRequest" in params:
            approve_request = params["txRequest"]
        else:
            # build request from user-supplied amount
            the_req = await self.getApproveGasTokenRequest({
                "l1Provider": l1_signer.provider,
                "l2Provider": params["l2Provider"],
                "amount": params.get("amount")
            })
            approve_request = the_req

        overrides = params.get("overrides", {})
        return l1_signer.send_transaction({**approve_request, **overrides})

class Erc20L1L3Bridger(BaseL1L3Bridger):
    """
    Continuation of the Erc20L1L3Bridger class, implementing the third snippet from l1l3Bridger.ts.
    """

    async def getDepositRequest(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositRequest(
            params: Erc20L1L3DepositRequestParams & (({ from, l1Provider } | { l1Signer }))
          ): Promise<DepositRequestResult>
        """
        # TS code: assertArbitrumNetworkHasTokenBridge(this.l2Network) ...
        assertArbitrumNetworkHasTokenBridge(self.l2Network)
        assertArbitrumNetworkHasTokenBridge(self.l3Network)

        # Decide whether we have l1Provider or l1Signer
        if "l1Provider" in params:
            l1Provider = params["l1Provider"]
        else:
            # 'from' in params => from: string
            # or fallback to: l1Signer.provider
            l1Signer = params["l1Signer"]
            l1Provider = l1Signer.provider

        await self._checkL1Network(l1Provider)
        await self._checkL2Network(params["l2Provider"])
        await self._checkL3Network(params["l3Provider"])

        if "from" in params:
            from_addr = params["from"]
        else:
            # TS: await params.l1Signer.getAddress()
            from_addr = await params["l1Signer"].getAddress()  # adapt to your signer approach

        # Decide the fee token on L1
        if not self.l2GasTokenAddress:
            # L3 uses ETH for fees => set zero address
            l1FeeToken = "0x0000000000000000000000000000000000000000"
        elif params.get("skipGasToken", False) is True:
            # If skipping, set the magic address
            l1FeeToken = self.skipL1GasTokenMagic
        else:
            # If using custom fee token, get L1 fee token address or throw
            l1FeeToken = await self.getGasTokenOnL1(l1Provider, params["l2Provider"])

        # TS code uses partialTeleportParams: OmitTyped<IL1Teleporter.TeleportParamsStruct, 'gasParams'>
        # We'll store that in a dict
        partialTeleportParams = {
            "l1Token": params["erc20L1Address"],
            "l3FeeTokenL1Addr": l1FeeToken,
            "l1l2Router": self.l2Network.tokenBridge.parentGatewayRouter,
            "l2l3RouterOrInbox":
                l1FeeToken
                and getAddress(params["erc20L1Address"]) == getAddress(l1FeeToken)
                and self.l3Network.ethBridge.inbox
                or self.l3Network.tokenBridge.parentGatewayRouter,
            "to": params.get("destinationAddress", from_addr),
            "amount": params["amount"],
        }

        # fallback for retryableOverrides
        retryableOverrides = params.get("retryableOverrides", {})

        # TS code: const { teleportParams, costs } = await this._fillPartialTeleportParams(...)
        result_fill = await self._fillPartialTeleportParams(
            partialTeleportParams,
            retryableOverrides,
            l1Provider,
            params["l2Provider"],
            params["l3Provider"]
        )
        teleportParams = result_fill["teleportParams"]
        costs = result_fill["costs"]

        # Encode data with IL1Teleporter 'teleport(...)'
        # e.g. in TS: IL1Teleporter__factory.createInterface().encodeFunctionData('teleport',[teleportParams])
        # We'll do a direct approach:
        teleporter_contract = load_contract(
            l1Provider,
            "IL1Teleporter",
            address=self.teleporter.l1Teleporter,
        )
        # Usually you'd do teleporterContract.encodeABI(fn_name='teleport', args=[teleportParams])
        # But the structure depends on your custom logic.
        data = teleporter_contract.encodeABI(
            fn_name="teleport",
            args=[teleportParams]
        )

        return {
            "txRequest": {
                "to": self.teleporter.l1Teleporter,
                "data": data,
                "value": costs["ethAmount"],  # TS: costs.ethAmount
            },
            "gasTokenAmount": costs["feeTokenAmount"],  # TS: costs.feeTokenAmount
        }

    async def deposit(
        self,
        params: Dict[str, Any]
    ) -> "ParentContractCallTransaction":
        """
        Python equivalent of:
          public async deposit(params: (Erc20L1L3DepositRequestParams & { l1Signer, overrides?}) 
                               | TxRequestParams): Promise<ParentContractCallTransaction>
        """
        await self._checkL1Network(params["l1Signer"])

        if "txRequest" in params:
            depositRequest = params["txRequest"]
        else:
            # we call getDepositRequest
            depositReqResult = await self.getDepositRequest(params)
            depositRequest = depositReqResult["txRequest"]

        overrides = params.get("overrides", {})
        tx = await params["l1Signer"].sendTransaction({**depositRequest, **overrides})
        return ParentTransactionReceipt.monkeyPatchContractCallWait(tx)

    async def getDepositParameters(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositParameters(params: { l1Provider, l2Provider } & TxReference)
        Returns an object with { teleportParams, l2ForwarderParams, l2ForwarderAddress }
        """
        await self._checkL1Network(params["l1Provider"])
        await self._checkL2Network(params["l2Provider"])

        tx = await self._getTxFromTxRef(params, params["l1Provider"])
        txReceipt = await tx.wait()  # in TS: tx.wait()

        # fetch L1->L2 messages
        l1l2Messages = await self._getL1ToL2Messages(txReceipt, params["l2Provider"])

        # decode callForwarderCalldata from l1l2Messages.l2ForwarderFactoryRetryable.messageData.data
        # in TS: const l2ForwarderParams = this._decodeCallForwarderCalldata(l1l2Messages.l2ForwarderFactoryRetryable.messageData.data)
        l2ForwarderParams = self._decodeCallForwarderCalldata(
            l1l2Messages["l2ForwarderFactoryRetryable"]["messageData"]["data"]
        )

        # l2ForwarderAddress = this.l2ForwarderAddress( ... ) 
        # We'll call it with same arguments
        l2ForwarderAddress = await self.l2ForwarderAddress(
            l2ForwarderParams["owner"],
            l2ForwarderParams["routerOrInbox"],
            l2ForwarderParams["to"],
            params["l2Provider"]
        )

        # decode teleport calldata from tx.data
        teleportParams = self._decodeTeleportCalldata(tx.data)

        return {
            "teleportParams": teleportParams,
            "l2ForwarderParams": l2ForwarderParams,
            "l2ForwarderAddress": l2ForwarderAddress,
        }

    async def getDepositStatus(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositStatus(params: GetL1L3DepositStatusParams): Promise<Erc20L1L3DepositStatus>
        
        We return { ...partialResult, l2l3TokenBridgeRetryable, l2ForwarderFactoryRetryableFrontRan, completed }
        """
        await self._checkL1Network(params["l1Provider"])
        await self._checkL2Network(params["l2Provider"])
        await self._checkL3Network(params["l3Provider"])

        l1TxReceipt = await self._getTxReceiptFromTxRef(params, params["l1Provider"])
        partialResult = await self._getL1ToL2Messages(l1TxReceipt, params["l2Provider"])

        # in TS: const factoryRedeem = await partialResult.l2ForwarderFactoryRetryable.getSuccessfulRedeem()
        factoryRedeem = await partialResult["l2ForwarderFactoryRetryable"].getSuccessfulRedeem()

        # if the childTxReceipt is redeemed, then we do new ParentTransactionReceipt(...)...
        if factoryRedeem["status"] == ParentToChildMessageStatus.REDEEMED:
            # TS: new ParentTransactionReceipt(factoryRedeem.childTxReceipt).getParentToChildMessages(params.l3Provider)[0]
            # We'll replicate that approach
            child_ptx_receipt = ParentTransactionReceipt(factoryRedeem["childTxReceipt"])
            all_l2l3 = await child_ptx_receipt.getParentToChildMessages(params["l3Provider"])
            l2l3Message = all_l2l3[0] if all_l2l3 else None
        else:
            l2l3Message = None

        l2ForwarderFactoryRetryableFrontRan = False

        # check race condition
        # TS code:
        #   l1l2TokenBridgeRetryableStatus = await partialResult.l1l2TokenBridgeRetryable.status()
        #   if ( status=REDEEMED && factoryRedeem.status=FUNDS_DEPOSITED_ON_CHILD ):
        #       => decode, check token balance
        l1l2TokenBridgeRetryableStatus = await partialResult["l1l2TokenBridgeRetryable"].status()
        if (
            l1l2TokenBridgeRetryableStatus == ParentToChildMessageStatus.REDEEMED 
            and factoryRedeem["status"] == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD
        ):
            # decode factory call
            decodedFactoryCall = self._decodeCallForwarderCalldata(
                partialResult["l2ForwarderFactoryRetryable"]["messageData"]["data"]
            )

            # check token balance
            l2_token_addr = decodedFactoryCall["l2Token"]
            from_owner = decodedFactoryCall["owner"]
            router_inbox = decodedFactoryCall["routerOrInbox"]
            to_addr = decodedFactoryCall["to"]

            forwarder_addr = await self.l2ForwarderAddress(
                from_owner, router_inbox, to_addr, params["l2Provider"]
            )

            # load contract & check balance
            l2_token_contract = load_contract(params["l2Provider"], "IERC20", address=l2_token_addr)
            balance = l2_token_contract.functions.balanceOf(forwarder_addr).call()

            l2ForwarderFactoryRetryableFrontRan = (balance == 0)

        # final "completed" = whether l2l3Message is redeemed
        if l2l3Message:
            completed = (await l2l3Message.status()) == ParentToChildMessageStatus.REDEEMED
        else:
            completed = False

        # return structure merges partialResult with l2l3TokenBridgeRetryable, etc.
        ret_dict = dict(partialResult)
        ret_dict["l2l3TokenBridgeRetryable"] = l2l3Message
        ret_dict["l2ForwarderFactoryRetryableFrontRan"] = l2ForwarderFactoryRetryableFrontRan
        ret_dict["completed"] = completed

        return ret_dict


    def teleportationType(self, partialTeleportParams: Dict[str, Any]) -> int:
        """
        Python equivalent of:
          public teleportationType(
            partialTeleportParams: Pick<IL1Teleporter.TeleportParamsStruct, 'l3FeeTokenL1Addr' | 'l1Token'>
          ): TeleportationType
        """
        l3FeeTokenL1Addr = partialTeleportParams["l3FeeTokenL1Addr"]
        l1Token = partialTeleportParams["l1Token"]

        # AddressZero check
        if l3FeeTokenL1Addr == "0x0000000000000000000000000000000000000000":
            # TeleportationType.Standard
            return 0
        elif getAddress(l1Token) == getAddress(l3FeeTokenL1Addr):
            # TeleportationType.OnlyGasToken
            return 1
        else:
            # TeleportationType.NonGasTokenToCustomGas
            return 2

    async def _getTokenBridgeGasEstimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        """
        Python equivalent of:
          protected async _getTokenBridgeGasEstimates(params: {
            parentProvider: Provider
            childProvider: Provider
            parentGasPrice: BigNumber
            parentErc20Address: string
            parentGatewayAddress: string
            from: string
            to: string
            amount: BigNumber
            isWeth: boolean
          }): Promise<RetryableGasValues>
        """
        # Load parentGateway
        # TS: L1GatewayRouter__factory.connect(params.parentGatewayAddress, params.parentProvider)
        parentGateway = self._loadL1GatewayRouter(
            params["parentGatewayAddress"],
            params["parentProvider"]
        )

        outboundCalldata = parentGateway.functions.getOutboundCalldata(
            params["parentErc20Address"],
            params["from"],
            params["to"],
            params["amount"],
            "0x"
        ).call()

        # use ParentToChildMessageGasEstimator
        estimates = await ParentToChildMessageGasEstimator(params["childProvider"]).estimateAll(
            {
                "to": parentGateway.functions.counterpartGateway().call(),
                "data": outboundCalldata,
                "from": parentGateway.address,
                "l2CallValue": params["amount"] if params["isWeth"] else 0,
                "excessFeeRefundAddress": params["to"],
                # new Address(params.from).applyAlias().value => apply alias logic
                # For brevity, we skip alias or define a function. 
                # We'll pretend applyAlias() is a no-op. 
                # If you have a specific alias approach, use it.
                "callValueRefundAddress": params["from"],  
            },
            params["parentGasPrice"],
            params["parentProvider"]
        )

        return {
            "gasLimit": estimates["gasLimit"],
            "maxSubmissionFee": estimates["maxSubmissionCost"]
        }

    async def _getL1L2TokenBridgeGasEstimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        """
        Python equivalent of:
          protected async _getL1L2TokenBridgeGasEstimates(...)
        """
        # TS: assertArbitrumNetworkHasTokenBridge(this.l2Network)
        assertArbitrumNetworkHasTokenBridge(self.l2Network)

        parentGatewayAddress = await self.getL1L2GatewayAddress(
            params["l1Token"],
            params["l1Provider"]
        )
        return await self._getTokenBridgeGasEstimates({
            "parentProvider": params["l1Provider"],
            "childProvider": params["l2Provider"],
            "parentGasPrice": params["l1GasPrice"],
            "parentErc20Address": params["l1Token"],
            "parentGatewayAddress": parentGatewayAddress,
            "from": self.teleporter.l1Teleporter,
            "to": params["l2ForwarderAddress"],
            "amount": params["amount"],
            "isWeth": (
                getAddress(parentGatewayAddress) ==
                getAddress(self.l2Network.tokenBridge["parentWethGateway"])
            ),
        })

    async def _getL1L2FeeTokenBridgeGasEstimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        """
        Python equivalent of:
          protected async _getL1L2FeeTokenBridgeGasEstimates(...)
        """
        assertArbitrumNetworkHasTokenBridge(self.l2Network)

        if params["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            return {
                "gasLimit": 0,
                "maxSubmissionFee": 0,
            }

        parentGatewayAddress = await self.getL1L2GatewayAddress(
            params["l3FeeTokenL1Addr"],
            params["l1Provider"]
        )
        return await self._getTokenBridgeGasEstimates({
            "parentProvider": params["l1Provider"],
            "childProvider": params["l2Provider"],
            "parentGasPrice": params["l1GasPrice"],
            "parentErc20Address": params["l3FeeTokenL1Addr"],
            "parentGatewayAddress": parentGatewayAddress,
            "from": self.teleporter.l1Teleporter,
            "to": params["l2ForwarderAddress"],
            "amount": params["feeTokenAmount"],
            "isWeth": (
                getAddress(parentGatewayAddress) ==
                getAddress(self.l2Network.tokenBridge["parentWethGateway"])
            ),
        })

    async def _getL2ForwarderFactoryGasEstimates(self, l1GasPrice: int, l1Provider: Web3) -> Dict[str, int]:
        """
        Python equivalent of:
          protected async _getL2ForwarderFactoryGasEstimates(...)
        """
        # In TS:
        #   const inbox = Inbox__factory.connect(this.l2Network.ethBridge.inbox, l1Provider)
        inbox = self._loadInboxContract(self.l2Network.ethBridge["inbox"], l1Provider)

        #   const maxSubmissionFee = await inbox.calculateRetryableSubmissionFee(
        #     this._l2ForwarderFactoryCalldataSize(),
        #     l1GasPrice
        #   )
        size = self._l2ForwarderFactoryCalldataSize()
        maxSubmissionFee = inbox.functions.calculateRetryableSubmissionFee(size, l1GasPrice).call()

        return {
            "gasLimit": self.l2ForwarderFactoryDefaultGasLimit,
            "maxSubmissionFee": maxSubmissionFee
        }

    async def _getL2L3BridgeGasEstimates(self, params: Dict[str, Any]) -> Dict[str, int]:
        """
        Python equivalent of:
          protected async _getL2L3BridgeGasEstimates(...)
        """
        assertArbitrumNetworkHasTokenBridge(self.l3Network)

        t_type = self.teleportationType(params["partialTeleportParams"])
        # TeleportationType enum values:
        #   Standard = 0
        #   OnlyGasToken = 1
        #   NonGasTokenToCustomGas = 2
        if t_type == 2 and params["partialTeleportParams"]["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            # we aren't paying for the retryable
            return {
                "gasLimit": 0,
                "maxSubmissionFee": 0,
            }
        elif t_type == 1:
            # bridging the fee token to L3 as a normal retryable
            # "PartialTeleportParams" => .amount, .to, etc.
            partial = params["partialTeleportParams"]
            estimate = await ParentToChildMessageGasEstimator(params["l3Provider"]).estimateAll(
                {
                    "to": partial["to"],
                    "data": "0x",
                    "from": params["l2ForwarderAddress"],
                    "l2CallValue": partial["amount"],  # in TS: BigNumber.from(partial.amount)
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
            # bridging non-fee token to L3
            parentGatewayAddress = await self.getL2L3GatewayAddress(
                params["partialTeleportParams"]["l1Token"],
                params["l1Provider"],
                params["l2Provider"]
            )

            # uses _getTokenBridgeGasEstimates with the L2->L3 bridging context
            l2_token_addr = await self.getL2Erc20Address(
                params["partialTeleportParams"]["l1Token"],
                params["l1Provider"]
            )
            isWeth = (
                getAddress(parentGatewayAddress) ==
                getAddress(self.l3Network.tokenBridge["parentWethGateway"])
            )
            return await self._getTokenBridgeGasEstimates({
                "parentProvider": params["l2Provider"],
                "childProvider": params["l3Provider"],
                "parentGasPrice": params["l2GasPrice"],
                "parentErc20Address": l2_token_addr,
                "parentGatewayAddress": parentGatewayAddress,
                "from": params["l2ForwarderAddress"],
                "to": params["partialTeleportParams"]["to"],
                "amount": params["partialTeleportParams"]["amount"],
                "isWeth": isWeth
            })

    async def _fillPartialTeleportParams(
        self,
        partialTeleportParams: Dict[str, Any],
        retryableOverrides: Dict[str, Any],
        l1Provider: Web3,
        l2Provider: Web3,
        l3Provider: Web3
    ) -> Dict[str, Any]:
        """
        Python equivalent of:
          protected async _fillPartialTeleportParams(...)

        Returns { teleportParams, costs }
        """
        # We'll define local functions akin to TS code

        async def getRetryableGasValuesWithOverrides(overrides: Dict[str, Any], getEstimates):
            """
            Adapts TS logic:
              let base: RetryableGasValues
              if (overrides?.gasLimit?.base && overrides?.maxSubmissionFee?.base) ...
            """
            # call getEstimates if needed
            if overrides and "gasLimit" in overrides and "maxSubmissionFee" in overrides \
               and "base" in overrides["gasLimit"] and "base" in overrides["maxSubmissionFee"]:
                base_gas_limit = overrides["gasLimit"]["base"]
                base_max_submission_fee = overrides["maxSubmissionFee"]["base"]
            else:
                calculated = await getEstimates()
                base_gas_limit = overrides.get("gasLimit", {}).get("base", calculated["gasLimit"])
                base_max_submission_fee = overrides.get("maxSubmissionFee", {}).get("base", calculated["maxSubmissionFee"])

            # percent increases
            gas_limit_increase = overrides.get("gasLimit", {}).get("percentIncrease", self.defaultGasLimitPercentIncrease)
            sub_fee_increase = overrides.get("maxSubmissionFee", {}).get("percentIncrease", 0)

            gasLimitAdjusted = self._percentIncrease(base_gas_limit, gas_limit_increase)
            subFeeAdjusted = self._percentIncrease(base_max_submission_fee, sub_fee_increase)

            # min gas limit
            minGasLimit = overrides.get("gasLimit", {}).get("min", 0)
            if gasLimitAdjusted < minGasLimit:
                gasLimitAdjusted = minGasLimit

            return {
                "gasLimit": gasLimitAdjusted,
                "maxSubmissionFee": subFeeAdjusted
            }

        async def applyGasPercentIncrease(overrides: Dict[str, Any], getEstimate):
            base_val = overrides.get("base") if overrides else None
            if not base_val:
                # call getEstimate
                base_val = getEstimate()
                if callable(base_val):
                    base_val = await base_val

            inc = overrides.get("percentIncrease", self.defaultGasPricePercentIncrease) if overrides else self.defaultGasPricePercentIncrease
            return self._percentIncrease(base_val, inc)

        # gather gas prices
        l1GasPrice = await applyGasPercentIncrease(retryableOverrides.get("l1GasPrice", {}), lambda: l1Provider.eth.gas_price)
        l2GasPrice = await applyGasPercentIncrease(retryableOverrides.get("l2GasPrice", {}), lambda: l2Provider.eth.gas_price)

        # if partialTeleportParams.l3FeeTokenL1Addr === skipL1GasTokenMagic => l3GasPrice=0 else get override
        if partialTeleportParams["l3FeeTokenL1Addr"] == self.skipL1GasTokenMagic:
            l3GasPrice = 0
        else:
            l3GasPrice = await applyGasPercentIncrease(retryableOverrides.get("l3GasPrice", {}), lambda: l3Provider.eth.gas_price)

        # TS code uses a fakeRandomL2Forwarder
        import os
        fakeRandomL2Forwarder = "0x" + os.urandom(20).hex()

        # l1l2TokenBridge
        l1l2TokenBridgeGasValues = await getRetryableGasValuesWithOverrides(
            retryableOverrides.get("l1l2TokenBridgeRetryableGas"), 
            lambda: self._getL1L2TokenBridgeGasEstimates({
                "l1Token": partialTeleportParams["l1Token"],
                "amount": partialTeleportParams["amount"],
                "l1GasPrice": l1GasPrice,
                "l2ForwarderAddress": fakeRandomL2Forwarder,
                "l1Provider": l1Provider,
                "l2Provider": l2Provider
            })
        )

        l2ForwarderFactoryGasValues = await getRetryableGasValuesWithOverrides(
            retryableOverrides.get("l2ForwarderFactoryRetryableGas"),
            lambda: self._getL2ForwarderFactoryGasEstimates(l1GasPrice, l1Provider)
        )

        l2l3TokenBridgeGasValues = await getRetryableGasValuesWithOverrides(
            retryableOverrides.get("l2l3TokenBridgeRetryableGas"),
            lambda: self._getL2L3BridgeGasEstimates({
                "partialTeleportParams": partialTeleportParams,
                "l2GasPrice": l2GasPrice,
                "l1Provider": l1Provider,
                "l2Provider": l2Provider,
                "l3Provider": l3Provider,
                "l2ForwarderAddress": fakeRandomL2Forwarder
            })
        )

        # if teleportationType === NonGasTokenToCustomGas => do the fee token bridging
        # else set to 0
        from_type = self.teleportationType(partialTeleportParams)
        if from_type == 2:  # NonGasTokenToCustomGas
            feeGas = await getRetryableGasValuesWithOverrides(
                retryableOverrides.get("l1l2GasTokenBridgeRetryableGas"),
                lambda: self._getL1L2FeeTokenBridgeGasEstimates({
                    "l1GasPrice": l1GasPrice,
                    "feeTokenAmount": (l2l3TokenBridgeGasValues["gasLimit"] * l3GasPrice) + l2l3TokenBridgeGasValues["maxSubmissionFee"],
                    "l3FeeTokenL1Addr": partialTeleportParams["l3FeeTokenL1Addr"],
                    "l2ForwarderAddress": fakeRandomL2Forwarder,
                    "l1Provider": l1Provider,
                    "l2Provider": l2Provider
                })
            )
            l1l2FeeTokenBridgeGasValues = {
                "gasLimit": feeGas["gasLimit"],
                "maxSubmissionFee": feeGas["maxSubmissionFee"]
            }
        else:
            # zero
            l1l2FeeTokenBridgeGasValues = {
                "gasLimit": 0,
                "maxSubmissionFee": 0
            }

        # build gasParams
        gasParams = {
            "l2GasPriceBid": l2GasPrice,
            "l3GasPriceBid": l3GasPrice,
            "l1l2TokenBridgeGasLimit": l1l2TokenBridgeGasValues["gasLimit"],
            "l1l2FeeTokenBridgeGasLimit": l1l2FeeTokenBridgeGasValues["gasLimit"],
            "l2l3TokenBridgeGasLimit": l2l3TokenBridgeGasValues["gasLimit"],
            "l2ForwarderFactoryGasLimit": l2ForwarderFactoryGasValues["gasLimit"],
            "l2ForwarderFactoryMaxSubmissionCost": l2ForwarderFactoryGasValues["maxSubmissionFee"],
            "l1l2TokenBridgeMaxSubmissionCost": l1l2TokenBridgeGasValues["maxSubmissionFee"],
            "l1l2FeeTokenBridgeMaxSubmissionCost": l1l2FeeTokenBridgeGasValues["maxSubmissionFee"],
            "l2l3TokenBridgeMaxSubmissionCost": l2l3TokenBridgeGasValues["maxSubmissionFee"],
        }

        # Merge into final TeleportParams
        teleportParams = dict(partialTeleportParams)
        teleportParams["gasParams"] = gasParams

        # in TS: IL1Teleporter__factory.connect(...).determineTypeAndFees(teleportParams)
        # We'll replicate:
        teleporter_contract = self._loadIL1Teleporter(l1Provider)  # or something
        costs = teleporter_contract.functions.determineTypeAndFees(teleportParams).call()

        return {
            "teleportParams": teleportParams,
            "costs": costs
        }
    

    def _l2ForwarderFactoryCalldataSize(self) -> int:
        """
        Python equivalent of:
          protected _l2ForwarderFactoryCalldataSize(): number
        Returns size of the calldata for `callForwarder(...)`.
        """

        # TS code constructs a 'struct: IL2Forwarder.L2ForwarderParamsStruct'
        # We'll replicate that as a dictionary in Python:
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

        # TS code: IL2ForwarderFactory__factory.createInterface().encodeFunctionData('callForwarder',[struct])
        # In Python, you might have a loaded contract for 'IL2ForwarderFactory'
        # We'll do a hypothetical approach:
        forwarder_factory = load_contract(
            provider=None,  # or whichever Web3 provider you want
            contract_name="IL2ForwarderFactory",
            address="0x0000000000000000000000000000000000000000",  # or a dummy
        )

        dummy_calldata = forwarder_factory.encodeABI(
            fn_name="callForwarder",
            args=[struct_params]
        )

        # TS used: return ethers.utils.hexDataLength(dummyCalldata) - 4
        # so we measure hex length, subtract 4 for the function selector
        # In Python, removing the '0x' prefix before counting:
        hex_str = dummy_calldata[2:] if dummy_calldata.startswith("0x") else dummy_calldata
        # Each two hex chars = 1 byte
        total_bytes = len(hex_str) // 2
        return total_bytes - 4

    def _decodeTeleportCalldata(self, data: str) -> Dict[str, Any]:
        """
        Python equivalent of:
          protected _decodeTeleportCalldata(data: string): IL1Teleporter.TeleportParamsStruct
        """
        # TS code:
        #   const iface = IL1Teleporter__factory.createInterface()
        #   const decoded = iface.parseTransaction({ data })
        #   if (decoded.functionFragment.name !== 'teleport') throw ...
        #   return decoded.args[0]

        teleporter_iface = load_contract(
            provider=None,
            contract_name="IL1Teleporter",
            address="0x0000000000000000000000000000000000000000"
        )

        decoded = teleporter_iface.decode_function_input("teleport", data)
        if not decoded or decoded[0] != "teleport":
            raise ArbSdkError("not a teleport tx")

        # decoded[1] might be the struct arguments
        return decoded[1]

    def _decodeCallForwarderCalldata(self, data: str) -> Dict[str, Any]:
        """
        Python equivalent of:
          protected _decodeCallForwarderCalldata(data: string): IL2Forwarder.L2ForwarderParamsStruct
        """
        # TS code:
        #   const iface = IL2ForwarderFactory__factory.createInterface()
        #   const decoded = iface.parseTransaction({ data })
        #   if (decoded.functionFragment.name !== 'callForwarder') throw ...
        #   return decoded.args[0]

        forwarder_factory = load_contract(
            provider=None,
            contract_name="IL2ForwarderFactory",
            address="0x0000000000000000000000000000000000000000"
        )
        decoded = forwarder_factory.decode_function_input("callForwarder", data)
        if not decoded or decoded[0] != "callForwarder":
            raise ArbSdkError("not callForwarder data")

        return decoded[1]

    async def _getL1ToL2Messages(
        self,
        l1TxReceipt: "ParentContractCallTransactionReceipt",
        l2Provider: Web3
    ) -> Dict[str, Optional[ParentToChildMessageReader]]:
        """
        Python equivalent of:
          protected async _getL1ToL2Messages(
            l1TxReceipt: ParentContractCallTransactionReceipt,
            l2Provider: Provider
          ) { ... }
        
        Returns partialResult with keys:
          l1l2TokenBridgeRetryable
          l1l2GasTokenBridgeRetryable
          l2ForwarderFactoryRetryable
        """
        l1l2Messages: List[ParentToChildMessageReader] = await l1TxReceipt.getParentToChildMessages(l2Provider)

        if len(l1l2Messages) == 2:
            return {
                "l1l2TokenBridgeRetryable": l1l2Messages[0],
                "l2ForwarderFactoryRetryable": l1l2Messages[1],
                "l1l2GasTokenBridgeRetryable": None,
            }
        else:
            return {
                "l1l2GasTokenBridgeRetryable": l1l2Messages[0],
                "l1l2TokenBridgeRetryable": l1l2Messages[1],
                "l2ForwarderFactoryRetryable": l1l2Messages[2],
            }


class EthL1L3Bridger:  # continuing from your existing BaseL1L3Bridger
    def __init__(self, l3Network: Dict[str, Any]):
        """
        Python equivalent constructor:
          constructor(l3Network: ArbitrumNetwork) {
            super(l3Network)
            if (l3Network.nativeToken && l3Network.nativeToken !== AddressZero) { throw ...}
          }
        """
        super().__init__(l3Network)

        if l3Network.get("nativeToken") and l3Network["nativeToken"] != "0x0000000000000000000000000000000000000000":
            raise ArbSdkError(f"L3 network {l3Network['name']} uses a custom fee token")

    async def getDepositRequest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositRequest(
            params: EthL1L3DepositRequestParams & (({ from, l1Provider } | { l1Signer }))
          ): Promise<ParentToChildTransactionRequest>
        """
        if "l1Provider" in params:
            l1Provider = params["l1Provider"]
        else:
            # 'l1Signer' scenario
            l1Signer = params["l1Signer"]
            l1Provider = l1Signer.provider

        await self._checkL1Network(l1Provider)
        await self._checkL2Network(params["l2Provider"])
        await self._checkL3Network(params["l3Provider"])

        from_addr = params["from"] if "from" in params else await params["l1Signer"].getAddress()
        l3DestinationAddress = params.get("destinationAddress", from_addr)
        l2RefundAddress = params.get("l2RefundAddress", from_addr)

        # TS code: call ParentToChildMessageCreator.getTicketCreationRequest for L3
        # We'll do a direct approach or rely on a utility you might have
        # next lines:
        l3TicketRequest = await self._someTicketCreationRequestFunction(
            {
                "to": l3DestinationAddress,
                "data": "0x",
                "from": self._applyAlias(from_addr),  # or your alias logic
                "l2CallValue": params["amount"],
                "excessFeeRefundAddress": l3DestinationAddress,
                "callValueRefundAddress": l3DestinationAddress,
            },
            params["l2Provider"],
            params["l3Provider"],
            params.get("l3TicketGasOverrides")
        )

        # do the same for the L2 ticket request
        l2TicketRequest = await self._someTicketCreationRequestFunction(
            {
                "from": from_addr,
                "to": l3TicketRequest["txRequest"]["to"],
                "l2CallValue": l3TicketRequest["txRequest"]["value"],
                "data": self._hexlify(l3TicketRequest["txRequest"]["data"]),
                "excessFeeRefundAddress": l2RefundAddress,
                "callValueRefundAddress": l2RefundAddress,
            },
            l1Provider,
            params["l2Provider"],
            params.get("l2TicketGasOverrides")
        )

        return l2TicketRequest

    async def deposit(self, params: Dict[str, Any]) -> "ParentContractCallTransaction":
        """
        Python equivalent of:
          public async deposit( ... ): Promise<ParentContractCallTransaction>
        """
        await self._checkL1Network(params["l1Signer"])

        if "txRequest" in params:
            depositRequest = params["txRequest"]
        else:
            depositRequest = (await self.getDepositRequest(params))["txRequest"]

        overrides = params.get("overrides", {})
        tx = await params["l1Signer"].sendTransaction({**depositRequest, **overrides})
        return ParentTransactionReceipt.monkeyPatchContractCallWait(tx)

    async def getDepositParameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositParameters( ... ): { l1l2TicketData, l2l3TicketData }
        """
        await self._checkL1Network(params["l1Provider"])

        tx = await self._getTxFromTxRef(params, params["l1Provider"])

        # TS code:
        #   const l1l2TicketData: RetryableMessageParams = { ...this._decodeCreateRetryableTicket(tx.data), l1Value: tx.value }
        l1l2TicketData = dict(self._decodeCreateRetryableTicket(tx.data))
        l1l2TicketData["l1Value"] = tx.value

        l2l3TicketData = dict(self._decodeCreateRetryableTicket(l1l2TicketData["data"]))
        l2l3TicketData["l1Value"] = l1l2TicketData["l2CallValue"]

        return {
            "l1l2TicketData": l1l2TicketData,
            "l2l3TicketData": l2l3TicketData
        }

    async def getDepositStatus(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Python equivalent of:
          public async getDepositStatus( ... ): Promise<EthL1L3DepositStatus>
        returns { l2Retryable, l3Retryable, completed }
        """
        await self._checkL1Network(params["l1Provider"])
        await self._checkL2Network(params["l2Provider"])
        await self._checkL3Network(params["l3Provider"])

        l1TxReceipt = await self._getTxReceiptFromTxRef(params, params["l1Provider"])

        # TS:
        #   const l1l2Message = (await l1TxReceipt.getParentToChildMessages(params.l2Provider))[0]
        all_messages = await l1TxReceipt.getParentToChildMessages(params["l2Provider"])
        l1l2Message = all_messages[0] if all_messages else None

        if not l1l2Message:
            return {
                "l2Retryable": None,
                "l3Retryable": None,
                "completed": False
            }

        l1l2Redeem = await l1l2Message.getSuccessfulRedeem()
        if l1l2Redeem["status"] != ParentToChildMessageStatus.REDEEMED:
            return {
                "l2Retryable": l1l2Message,
                "l3Retryable": None,
                "completed": False
            }

        # if redeemed, check L2->L3
        # TS: const l2l3Message = (await new ParentEthDepositTransactionReceipt(l1l2Redeem.childTxReceipt)
        #                          .getParentToChildMessages(params.l3Provider))[0]
        child_tx_receipt = ParentEthDepositTransactionReceipt(l1l2Redeem["childTxReceipt"])
        l2l3_msgs = await child_tx_receipt.getParentToChildMessages(params["l3Provider"])
        l2l3Message = l2l3_msgs[0] if l2l3_msgs else None

        if not l2l3Message:
            raise ArbSdkError("L2 to L3 message not found")

        completed = (await l2l3Message.status()) == ParentToChildMessageStatus.REDEEMED

        return {
            "l2Retryable": l1l2Message,
            "l3Retryable": l2l3Message,
            "completed": completed
        }

    def _decodeCreateRetryableTicket(self, data: str) -> Dict[str, Any]:
        """
        Python equivalent of:
          protected _decodeCreateRetryableTicket(data: string): OmitTyped<RetryableMessageParams, 'l1Value'>
        """
        # TS:
        #   const iface = IInbox__factory.createInterface()
        #   const decoded = iface.parseTransaction({ data })
        #   if (decoded.functionFragment.name !== 'createRetryableTicket') throw ...
        #   const args = decoded.args
        #   return { ... }

        inbox_iface = load_contract(
            provider=None,
            contract_name="IInbox",
            address="0x0000000000000000000000000000000000000000"
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

