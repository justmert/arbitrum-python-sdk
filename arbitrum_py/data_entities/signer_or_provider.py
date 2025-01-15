from typing import Literal, Optional, Union, cast, overload

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import Address, BlockNumber, ChecksumAddress, Hash32, HexStr
from hexbytes import HexBytes
from web3 import Web3
from web3.types import ENS, BlockData, TxData, TxParams, TxReceipt, Wei

from arbitrum_py.data_entities.errors import ArbSdkError, MissingProviderArbSdkError


class SignerOrProvider:
    """A combined signer and provider for Ethereum transactions.

    This class provides a unified interface for both signing transactions and
    interacting with an Ethereum network. It combines the functionality of
    eth_account's LocalAccount (signer) and Web3 (provider).

    In the TypeScript SDK, this was represented as a union type (Signer | Provider).
    In Python, we implement it as a class that can optionally contain both components.

    Attributes:
        account (Optional[LocalAccount]): The account that can sign transactions
        provider (Optional[Web3]): The Web3 instance for sending transactions

    Example:
        >>> from eth_account import Account
        >>> from web3 import Web3
        >>>
        >>> # Create with both signer and provider
        >>> account = Account.create()
        >>> w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
        >>> signer_provider = SignerOrProvider(account=account, provider=w3)
        >>>
        >>> # Get current balance
        >>> balance = signer_provider.get_balance()
        >>>
        >>> # Sign and send a transaction
        >>> tx = {'to': '0x...', 'value': 1000000000000000000}
        >>> signed = signer_provider.sign_transaction(tx)
        >>> tx_hash = signer_provider.provider.eth.send_raw_transaction(signed)
    """

    def __init__(self, account: Optional[LocalAccount] = None, provider: Optional[Web3] = None) -> None:
        """Initialize a new SignerOrProvider instance.

        Args:
            account: A LocalAccount that can sign messages and transactions
            provider: A Web3 instance connected to an Ethereum network
        """
        self.account = account
        self.provider = provider
        self.eth = SignerProviderUtils.get_provider_or_throw(self.provider).eth

    def get_address(self) -> HexStr:
        """Get the address of the signer account.

        Returns:
            The checksummed address of the signer account

        Raises:
            AttributeError: If no account is set
        """
        if not self.account:
            raise AttributeError("No account set")
        return cast(HexStr, self.account.address)

    @property
    def address(self) -> HexStr:
        """The checksummed address of the signer account.

        Returns:
            The account's address

        Raises:
            AttributeError: If no account is set
        """
        return self.get_address()

    def sign_message(self, message: bytes) -> bytes:
        """Sign a message using the signer account.

        Args:
            message: The message to sign

        Returns:
            The signature bytes

        Raises:
            AttributeError: If no account is set
        """
        if not self.account:
            raise AttributeError("No account set")
        return cast(bytes, self.account.sign_message(message))

    def sign_transaction(self, transaction: TxParams) -> bytes:
        """Sign a transaction using the signer account.

        Args:
            transaction: The transaction parameters to sign

        Returns:
            The signed transaction bytes ready for sending

        Raises:
            AttributeError: If no account is set
        """
        if not self.account:
            raise AttributeError("No account set")
        return cast(bytes, self.account.sign_transaction(transaction))

    def get_chain_id(self) -> int:
        """Get the chain ID of the connected network.

        Returns:
            The chain ID

        Raises:
            AttributeError: If no provider is set
        """
        if not self.provider:
            raise AttributeError("No provider set")
        return self.provider.eth.chain_id

    @property
    def chain_id(self) -> int:
        """The chain ID of the connected network.

        Returns:
            The chain ID

        Raises:
            AttributeError: If no provider is set
        """
        return self.get_chain_id()

    @overload
    def get_balance(self) -> Wei: ...

    @overload
    def get_balance(self, block_identifier: Union[BlockNumber, str]) -> Wei: ...

    def get_balance(self, block_identifier: Optional[Union[BlockNumber, str]] = None) -> Wei:
        """Get the balance of the signer account.

        Args:
            block_identifier: The block number or block tag to get balance at.
                Defaults to 'latest'

        Returns:
            The balance in wei

        Raises:
            AttributeError: If no provider is set or no account is set
        """
        if not self.provider:
            raise AttributeError("No provider set")
        if not self.account:
            raise AttributeError("No account set")
        address = cast(Union[Address, ChecksumAddress, ENS], self.address)
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.get_balance(address, block)

    @property
    def balance(self) -> Wei:
        """The current balance of the signer account.

        Returns:
            The balance in wei

        Raises:
            AttributeError: If no provider is set or no account is set
        """
        return self.get_balance()

    def get_nonce(self, block_identifier: Optional[Union[BlockNumber, str]] = None) -> int:
        """
        Get the nonce of the signer account.
        :param block_identifier: The block identifier to get the nonce at a specific block.
        :return: The nonce of the signer account.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        if not self.account:
            raise AttributeError("No account set")
        address = cast(Union[Address, ChecksumAddress, ENS], self.address)
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.get_transaction_count(address, block)

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
        if not self.provider:
            raise AttributeError("No provider set")
        return self.provider.eth.gas_price

    def estimate_gas(self, transaction: TxParams, block_identifier: Optional[Union[BlockNumber, str]] = None) -> int:
        """
        Estimate the gas for a transaction.
        :param transaction: The transaction to estimate the gas for.
        :return: The estimated gas for the transaction.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.estimate_gas(transaction, block)

    def get_block_number(self) -> int:
        """
        Get the block number of the provider.
        :return: The block number of the provider.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        return self.provider.eth.block_number

    def get_block(self, block_identifier: Optional[Union[BlockNumber, str]] = None) -> BlockData:
        """
        Get the block information.
        :param block_identifier: The block identifier to get the block information.
        :return: The block information.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        block = cast(
            Union[
                Literal["latest", "earliest", "pending", "safe", "finalized"],
                BlockNumber,
                Hash32,
                HexStr,
                HexBytes,
                int,
            ],
            block_identifier if block_identifier is not None else "latest",
        )
        return cast(BlockData, self.provider.eth.get_block(block))

    def get_transaction(self, transaction_hash: Hash32) -> TxData:
        """
        Get the transaction information.
        :param transaction_hash: The transaction hash to get the transaction information.
        :return: The transaction information.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        return cast(TxData, self.provider.eth.get_transaction(transaction_hash))

    def get_transaction_receipt(self, transaction_hash: Hash32) -> TxReceipt:
        """
        Get the transaction receipt.
        :param transaction_hash: The transaction hash to get the transaction receipt.
        :return: The transaction receipt.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        return self.provider.eth.get_transaction_receipt(transaction_hash)

    def send_transaction(self, transaction: TxParams) -> Hash32:
        """
        Send a transaction.
        :param transaction: The transaction to send.
        :return: The transaction hash.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        result = self.provider.eth.send_transaction(transaction)
        return cast(Hash32, result)

    def call(
        self,
        transaction: TxParams,
        block_identifier: Optional[Union[BlockNumber, str]] = None,
    ) -> bytes:
        """
        Call a transaction.
        :param transaction: The transaction to call.
        :return: The result of the call.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.call(transaction, block)

    def get_code(self, address: HexStr, block_identifier: Optional[Union[BlockNumber, str]] = None) -> bytes:
        """
        Get the code of an address.
        :param address: The address to get the code for.
        :return: The code of the address.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        addr = cast(Union[Address, ChecksumAddress, ENS], address)
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.get_code(addr, block)

    def get_transaction_count(self, address: HexStr, block_identifier: Optional[Union[BlockNumber, str]] = None) -> int:
        """
        Get the transaction count of an address.
        :param address: The address to get the transaction count for.
        :return: The transaction count of the address.
        """
        if not self.provider:
            raise AttributeError("No provider set")
        addr = cast(Union[Address, ChecksumAddress, ENS], address)
        block = cast(
            Optional[
                Union[
                    Literal["latest", "earliest", "pending", "safe", "finalized"],
                    BlockNumber,
                    Hash32,
                    HexStr,
                    HexBytes,
                    int,
                ]
            ],
            block_identifier,
        )
        return self.provider.eth.get_transaction_count(addr, block)


class SignerProviderUtils:
    """Utility functions for handling signer and provider objects.

    This class provides static methods for working with SignerOrProvider instances
    and their components. It helps determine what capabilities are available and
    ensures proper provider/signer access.

    The methods in this class mirror the functionality of the TypeScript SDK's
    SignerProviderUtils, but adapted for Python's type system and web3.py
    conventions.
    """

    @staticmethod
    def is_signer(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> bool:
        """Check if an object is a signer.

        In TypeScript, signers are detected by checking for the signMessage method.
        In Python, we check for LocalAccount/Account or SignerOrProvider with an
        account.

        Args:
            signer_or_provider: Object to check - could be a Web3 provider,
                a local signer, or a SignerOrProvider instance

        Returns:
            True if the object can sign transactions, False otherwise

        Example:
            >>> account = Account.create()
            >>> SignerProviderUtils.is_signer(account)  # True
            >>> w3 = Web3(Web3.HTTPProvider('...'))
            >>> SignerProviderUtils.is_signer(w3)  # False
        """

        signer = SignerProviderUtils.get_signer(signer_or_provider)
        return signer is not None

    @staticmethod
    def get_signer(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Optional[LocalAccount]:
        """Get the signer from a signer/provider object if available.

        Args:
            signer_or_provider: Object that might contain a signer

        Returns:
            The LocalAccount signer if available, None otherwise
        """
        if isinstance(signer_or_provider, LocalAccount):
            return signer_or_provider
        if isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.account
        return None

    @staticmethod
    def get_signer_or_throw(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> LocalAccount:
        """Get the signer from an object or raise an error.

        Args:
            signer_or_provider: Object that should contain a signer

        Returns:
            The LocalAccount signer

        Raises:
            MissingProviderArbSdkError: If no signer is found
        """
        signer = SignerProviderUtils.get_signer(signer_or_provider)
        if not signer:
            raise MissingProviderArbSdkError("signer_or_provider")
        return signer

    @staticmethod
    def get_provider(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Optional[Web3]:
        """Get the provider from a signer/provider object if available.

        Args:
            signer_or_provider: Object that might contain a provider

        Returns:
            The Web3 provider if available, None otherwise
        """
        if isinstance(signer_or_provider, Web3):
            return signer_or_provider
        if isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.provider
        return None

    @staticmethod
    def get_provider_or_throw(signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3]) -> Web3:
        """Get the provider from an object or raise an error.

        Args:
            signer_or_provider: Object that should contain a provider

        Returns:
            The Web3 provider

        Raises:
            MissingProviderArbSdkError: If no provider is found
        """
        provider = SignerProviderUtils.get_provider(signer_or_provider)
        if not provider:
            raise MissingProviderArbSdkError("signer_or_provider")
        return provider

    @staticmethod
    def signer_has_provider(signer: Union[LocalAccount, SignerOrProvider]) -> bool:
        """Check if a signer object also has an associated provider.

        Args:
            signer: A signer object to check

        Returns:
            True if the signer has an associated provider, False otherwise
        """
        if isinstance(signer, SignerOrProvider):
            return signer.provider is not None
        return False

    @staticmethod
    def check_network_matches(
        signer_or_provider: Union[SignerOrProvider, LocalAccount, Account, Web3], chain_id: int
    ) -> None:
        """Check if a provider is connected to the expected network.

        Verifies that the provider's network matches the expected chain ID.
        This is important for ensuring transactions are sent to the correct
        network.

        Args:
            signer_or_provider: Object containing a provider to check
            chain_id: The expected chain ID

        Raises:
            MissingProviderArbSdkError: If no provider is found
            ArbSdkError: If the chain ID doesn't match

        Example:
            >>> w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
            >>> # Check we're on mainnet (chain_id=1)
            >>> SignerProviderUtils.check_network_matches(w3, 1)
        """
        provider = SignerProviderUtils.get_provider(signer_or_provider)
        if not provider:
            raise MissingProviderArbSdkError("signer_or_provider")

        provider_chain_id = provider.eth.chain_id
        if provider_chain_id != chain_id:
            raise ArbSdkError(
                f"Signer/provider chain id: {provider_chain_id} does not match expected chain id: {chain_id}."
            )
