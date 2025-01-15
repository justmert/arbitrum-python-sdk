from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from arbitrum_py.data_entities.errors import ArbSdkError
from arbitrum_py.data_entities.networks import (
    ArbitrumNetwork,
    is_arbitrum_network_native_token_ether,
)
from arbitrum_py.data_entities.signer_or_provider import (
    SignerOrProvider,
    SignerProviderUtils,
)
from arbitrum_py.message.child_transaction import ChildContractTransaction
from arbitrum_py.message.parent_transaction import ParentContractTransaction

DepositParams = TypeVar("DepositParams")
WithdrawParams = TypeVar("WithdrawParams")


class AssetBridger(ABC, Generic[DepositParams, WithdrawParams]):
    """Base class for bridging assets between parent and child chains.

    This abstract base class provides the foundation for implementing asset bridging
    functionality between parent (L1-like) and child (L2-like) chains in the Arbitrum
    ecosystem. It handles basic network validation and provides abstract methods for
    deposit and withdrawal operations.

    Attributes:
        child_network (ArbitrumNetwork): Network configuration for the child chain
        native_token (Optional[str]): Address of the native token on the parent chain.
            - For chains using ETH as native token: None or zero address
            - For chains using ERC-20 as native token: Address of token on parent chain
    """

    def __init__(self, child_network: ArbitrumNetwork) -> None:
        """Initialize the AssetBridger.

        Args:
            child_network: ArbitrumNetwork instance containing chain configuration
                including chain IDs and network properties.

        Raises:
            ArbSdkError: If child_network is invalid or parent chain ID is undefined
        """
        if not child_network or not hasattr(child_network, "parentChainId"):
            raise ArbSdkError("Invalid or missing child_network object.")

        if child_network.parentChainId is None:
            raise ArbSdkError(f"Unknown parent chain ID: {child_network.parentChainId}")

        self.child_network = child_network
        self.native_token: Optional[str] = child_network.nativeToken

    def check_parent_network(self, sop: SignerOrProvider) -> None:
        """Verify the signer/provider matches the parent network.

        Args:
            sop: SignerOrProvider instance for the parent chain

        Raises:
            ArbSdkError: If the network does not match child_network.parent_chain_id
        """
        SignerProviderUtils.check_network_matches(sop, self.child_network.parentChainId)

    def check_child_network(self, sop: SignerOrProvider) -> None:
        """Verify the signer/provider matches the child network.

        Args:
            sop: SignerOrProvider instance for the child chain

        Raises:
            ArbSdkError: If the network does not match child_network.chain_id
        """
        SignerProviderUtils.check_network_matches(sop, self.child_network.chainId)

    @property
    def native_token_is_eth(self) -> bool:
        """Check if the child network uses ETH as its native token.

        Returns:
            bool: True if the native token is ETH, False if it's an ERC-20 token
        """
        return is_arbitrum_network_native_token_ether(self.child_network)

    @abstractmethod
    def deposit(self, params: DepositParams) -> ParentContractTransaction:
        """Transfer assets from parent chain to child chain.

        Args:
            params: Parameters required for the deposit operation

        Returns:
            ParentContractTransaction: Transaction object for the deposit

        Raises:
            ArbSdkError: If the deposit operation fails
        """
        pass

    @abstractmethod
    def withdraw(self, params: WithdrawParams) -> ChildContractTransaction:
        """Transfer assets from child chain to parent chain.

        Args:
            params: Parameters required for the withdrawal operation

        Returns:
            ChildContractTransaction: Transaction object for the withdrawal

        Raises:
            ArbSdkError: If the withdrawal operation fails
        """
        pass
