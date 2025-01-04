from abc import ABC, abstractmethod

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import is_arbitrum_network_native_token_ether
from src.lib.data_entities.signer_or_provider import SignerProviderUtils
from src.lib.data_entities.networks import ArbitrumNetwork

class AssetBridger(ABC):
    """
    Base class for bridging assets from a parent chain to a child chain (and back).
    Replaces the old L1->L2 bridging concept with v4 parent->child terminology.
    """

    def __init__(self, child_network: ArbitrumNetwork):
        """
        Initialize the AssetBridger.

        :param child_network: ArbitrumNetwork (v4) instance describing the child chain
                              (including child_network.chain_id, child_network.parent_chain_id, etc.)
        :raises ArbSdkError: If the parent chain ID is invalid or undefined
        """
        if not child_network or not hasattr(child_network, "parent_chain_id"):
            raise ArbSdkError("Invalid or missing child_network object.")
        
        if child_network.parentChainId is None:
            raise ArbSdkError(f"Unknown parent chain ID: {child_network.parentChainId}")

        self.child_network = child_network

        # In v4, child_network may have a .native_token property describing
        # which token is used as the native currency on this chain (ETH or an ERC-20).
        self.native_token = child_network.nativeToken

    async def check_parent_network(self, sop):
        """
        Checks if the signer/provider matches the parent (L1) network by comparing chain IDs.
        Throws an exception if it does not match.

        :param sop: SignerOrProvider instance for the parent chain
        :raises ArbSdkError: If the network does not match child_network.parent_chain_id
        """
        await SignerProviderUtils.check_network_matches(sop, self.child_network.parentChainId)

    async def check_child_network(self, sop):
        """
        Checks if the signer/provider matches the child (L2 or orbit) network by comparing chain IDs.
        Throws an exception if it does not match.

        :param sop: SignerOrProvider instance for the child chain
        :raises ArbSdkError: If the network does not match child_network.chain_id
        """
        await SignerProviderUtils.check_network_matches(sop, self.child_network.chainId)

    @property
    def native_token_is_eth(self) -> bool:
        """
        Whether this child network uses ETH as its native token.
        For some Orbit chains, the native token may be an ERC-20 instead.

        :return: True if native token is ETH, False otherwise
        """
        return is_arbitrum_network_native_token_ether(self.child_network)

    @abstractmethod
    async def deposit(self, params):
        """
        Transfer assets from the parent chain to the child chain.

        :param params: A dictionary or object specifying deposit parameters (e.g., token address, amount)
        :return: Typically a ParentContractTransaction (analogous to L1ContractTransaction in old code)
        :raises ArbSdkError: If any checks fail or transaction reverts
        """
        pass

    @abstractmethod
    async def withdraw(self, params):
        """
        Transfer assets from the child chain back to the parent chain.

        :param params: A dictionary or object specifying withdrawal parameters
        :return: Typically a ChildContractTransaction (analogous to L2ContractTransaction in old code)
        :raises ArbSdkError: If any checks fail or transaction reverts
        """
        pass
