from typing import Optional, Union
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError


class SignerOrProvider:
    """
    A Python class representing a union of a "signer" and/or "provider".
    In TypeScript, this was a union type: 'Signer | Provider'.

    This class simply stores 'account' and 'provider'. 
    If you have a 'LocalAccount', you set 'account', and if you have a 'Web3' object, you set 'provider', etc.
    """

    def __init__(
        self,
        account: Optional[LocalAccount] = None,
        provider: Optional[Web3] = None
    ):
        """
        :param account: A LocalAccount or similar object that can sign messages
        :param provider: A Web3 object that can send RPC requests
        """
        self.account = account
        self.provider = provider


class SignerProviderUtils:
    """
    Utility functions that handle the logic of 'signer or provider' usage,
    analogous to the TypeScript 'SignerProviderUtils'.
    """

    @staticmethod
    def is_signer(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> bool:
        """
        Check if the input is effectively a 'signer'.
        In TS, we do 'isDefined(signer.signMessage)' to detect signers.
        In Python, we check for LocalAccount/Account or a SignerOrProvider with an 'account'.

        :param signer_or_provider: A union that might be a local signer or a web3 provider.
        :return: True if it is some type of signer, False otherwise.
        """
        if isinstance(signer_or_provider, LocalAccount):
            return True
        if isinstance(signer_or_provider, Account):
            return True
        if isinstance(signer_or_provider, SignerOrProvider) and signer_or_provider.account is not None:
            return True
        return False

    @staticmethod
    def get_signer(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Optional[Account]:
        """
        If 'signer_or_provider' is effectively a signer, return it.
        If it's a provider, attempt to get the underlying signer, else None.

        :param signer_or_provider: Could be a Web3 provider, a local signer, or the SignerOrProvider class.
        :return: The signer object if a signer is available, or None otherwise.
        """
        if isinstance(signer_or_provider, LocalAccount):
            return signer_or_provider
        elif isinstance(signer_or_provider, Account):
            return signer_or_provider
        elif isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.account
        return None
    
    @staticmethod
    def get_signer_or_throw(
        signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]
    ) -> Account:
        """
        Same as get_signer(...) but throws an error if no signer is found.

        :param signer_or_provider: Potential signer or provider
        :return: A LocalAccount signer
        :raises MissingProviderArbSdkError if no signer is found.
        """
        signer = SignerProviderUtils.get_signer(signer_or_provider)
        if not signer:
            raise MissingProviderArbSdkError("signerOrProvider")
        return signer

    @staticmethod
    def get_provider(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Optional[Web3]:
        """
        If 'signer_or_provider' is effectively a provider, return it.
        If it's a signer, attempt to get the underlying provider, else None.

        :param signer_or_provider: Could be a Web3 provider, a local signer, or the SignerOrProvider class.
        :return: The Web3 object if a provider is available, or None otherwise.
        """
        if isinstance(signer_or_provider, Web3):
            return signer_or_provider
        elif isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.provider
        elif isinstance(signer_or_provider, (LocalAccount, Account)):
            # local signers don't inherently have a provider
            return None
        return None

    @staticmethod
    def get_provider_or_throw(
        signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]
    ) -> Web3:
        """
        Same as get_provider(...) but throws an error if no provider is found.

        :param signer_or_provider: Potential signer or provider
        :return: A Web3 provider
        :raises MissingProviderArbSdkError if no provider is found.
        """
        provider = SignerProviderUtils.get_provider(signer_or_provider)
        if not provider:
            raise MissingProviderArbSdkError("signerOrProvider")
        return provider

    @staticmethod
    def signer_has_provider(signer: Union[LocalAccount, SignerOrProvider]) -> bool:
        """
        Check if the signer object also contains a provider. 
        In TS, we do 'isDefined(signer.provider)'.

        :param signer: Either a local account or a SignerOrProvider
        :return: True if it is a SignerOrProvider with a non-empty provider, else False.
        """
        if isinstance(signer, SignerOrProvider) and signer.provider is not None:
            return True
        return False

    @staticmethod
    async def check_network_matches(
        signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3],
        chain_id: int
    ) -> None:
        """
        Check that the provided signer or provider is connected to a network with the specified chain_id.
        Throw an error if it doesn't match.

        :param signer_or_provider: The potential signer or provider.
        :param chain_id: The chain ID we expect.
        :raises MissingProviderArbSdkError: If no provider is found on the object.
        :raises ArbSdkError: If the chain id doesn't match.
        """
        provider = SignerProviderUtils.get_provider(signer_or_provider)
        if provider is None:
            raise MissingProviderArbSdkError("signerOrProvider")

        # For consistency, we rely on 'provider.eth.chain_id' to get the chainId
        provider_chain_id = provider.eth.chain_id
        if provider_chain_id != chain_id:
            raise ArbSdkError(
                f"Signer/provider chain id: {provider_chain_id} does not match expected chain id: {chain_id}."
            )
