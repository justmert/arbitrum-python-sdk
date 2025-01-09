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

    def __init__(self, account: Optional[LocalAccount] = None, provider: Optional[Web3] = None):
        """
        :param account: A LocalAccount or similar object that can sign messages
        :param provider: A Web3 object that can send RPC requests
        """
        self.account = account
        self.provider = provider

    def get_address(self) -> str:
        """
        Get the address of the signer account.
        :return: The address of the signer account.
        """
        return self.account.address

    @property
    def address(self) -> str:
        """
        Get the address of the signer account.
        :return: The address of the signer account.
        """
        return self.get_address()

    def sign_message(self, message: bytes) -> bytes:
        """
        Sign a message using the signer account.
        :param message: The message to sign.
        :return: The signature of the message.
        """
        return self.account.sign_message(message)

    def sign_transaction(self, transaction: dict) -> bytes:
        """
        Sign a transaction using the signer account.
        :param transaction: The transaction to sign.
        :return: The signed transaction.
        """
        return self.account.sign_transaction(transaction)

    def get_chain_id(self) -> int:
        """
        Get the chain ID of the provider.
        :return: The chain ID of the provider.
        """
        return self.provider.eth.chain_id

    @property
    def chain_id(self) -> int:
        """
        Get the chain ID of the provider.
        :return: The chain ID of the provider.
        """
        return self.get_chain_id()

    def get_balance(self, block_identifier: Optional[Union[int, str]] = None) -> int:
        """
        Get the balance of an address.
        :param block_identifier: The block identifier to get the balance at a specific block.
        :return: The balance of the address.
        """
        return self.provider.eth.get_balance(self.address, block_identifier)

    @property
    def balance(self) -> int:
        """
        Get the balance of the signer account.
        :return: The balance of the signer account.
        """
        return self.get_balance(self.get_address())

    def get_nonce(self, block_identifier: Optional[Union[int, str]] = None) -> int:
        """
        Get the nonce of the signer account.
        :param block_identifier: The block identifier to get the nonce at a specific block.
        :return: The nonce of the signer account.
        """
        return self.provider.eth.get_transaction_count(self.address, block_identifier)

    @property
    def nonce(self) -> int:
        """
        Get the nonce of the signer account.
        :return: The nonce of the signer account.
        """
        return self.get_nonce()

    def get_gas_price(self) -> int:
        """
        Get the gas price of the provider.
        :return: The gas price of the provider.
        """
        return self.provider.eth.gas_price

    def estimate_gas(self, transaction: dict, block_identifier: Optional[Union[int, str]] = None) -> int:
        """
        Estimate the gas for a transaction.
        :param transaction: The transaction to estimate the gas for.
        :return: The estimated gas for the transaction.
        """
        return self.provider.eth.estimate_gas(transaction, block_identifier)

    def get_block_number(self) -> int:
        """
        Get the block number of the provider.
        :return: The block number of the provider.
        """
        return self.provider.eth.block_number

    def get_block(self, block_identifier: Optional[Union[int, str]] = None) -> dict:
        """
        Get the block information.
        :param block_identifier: The block identifier to get the block information.
        :return: The block information.
        """
        return self.provider.eth.get_block(block_identifier)

    def get_transaction(self, transaction_hash: str) -> dict:
        """
        Get the transaction information.
        :param transaction_hash: The transaction hash to get the transaction information.
        :return: The transaction information.
        """
        return self.provider.eth.get_transaction(transaction_hash)

    def get_transaction_receipt(self, transaction_hash: str) -> dict:
        """
        Get the transaction receipt.
        :param transaction_hash: The transaction hash to get the transaction receipt.
        :return: The transaction receipt.
        """
        return self.provider.eth.get_transaction_receipt(transaction_hash)

    def send_transaction(self, transaction: dict) -> str:
        """
        Send a transaction.
        :param transaction: The transaction to send.
        :return: The transaction hash.
        """
        return self.provider.eth.send_transaction(transaction)

    def call(
        self,
        transaction: dict,
        block_identifier: Optional[Union[int, str]] = None,
    ) -> bytes:
        """
        Call a transaction.
        :param transaction: The transaction to call.
        :return: The result of the call.
        """
        return self.provider.eth.call(transaction, block_identifier)

    def get_code(self, address: str, block_identifier: Optional[Union[int, str]] = None) -> bytes:
        """
        Get the code of an address.
        :param address: The address to get the code for.
        :return: The code of the address.
        """
        return self.provider.eth.get_code(address, block_identifier)

    def get_transaction_count(self, address: str, block_identifier: Optional[Union[int, str]] = None) -> int:
        """
        Get the transaction count of an address.
        :param address: The address to get the transaction count for.
        :return: The transaction count of the address.
        """
        return self.get_nonce(address, block_identifier)


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
    def get_signer_or_throw(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Account:
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
    def get_provider_or_throw(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Web3:
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
    def check_network_matches(
        signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3], chain_id: int
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
