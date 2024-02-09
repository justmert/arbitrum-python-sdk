from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError, MissingProviderArbSdkError


class SignerOrProvider:
    def __init__(self, account, provider):
        self.account = account
        self.provider = provider


class SignerProviderUtils:
    @staticmethod
    def is_signer(signer_or_provider):
        if isinstance(signer_or_provider, LocalAccount):
            return True

        elif isinstance(signer_or_provider, Account):
            return True

        elif isinstance(signer_or_provider, SignerOrProvider):
            return True

        elif isinstance(signer_or_provider, Web3):
            return False

        else:
            return False

    @staticmethod
    def get_provider(signer_or_provider):
        if isinstance(signer_or_provider, Web3):
            return signer_or_provider

        elif isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.provider

        elif isinstance(signer_or_provider, LocalAccount):
            return None

        elif isinstance(signer_or_provider, Account):
            return None

        else:
            return None

    @staticmethod
    def get_signer(signer_or_provider):
        if isinstance(signer_or_provider, LocalAccount):
            return signer_or_provider

        elif isinstance(signer_or_provider, Account):
            return signer_or_provider

        elif isinstance(signer_or_provider, SignerOrProvider):
            return signer_or_provider.account

        elif isinstance(signer_or_provider, Web3):
            return None

        else:
            return None

    @staticmethod
    def get_provider_or_throw(signer_or_provider):
        provider = SignerProviderUtils.get_provider(signer_or_provider)
        if provider:
            return provider
        else:
            raise MissingProviderArbSdkError(signer_or_provider)

    @staticmethod
    def signer_has_provider(signer):
        return isinstance(signer, SignerOrProvider)

    @staticmethod
    async def check_network_matches(signer_or_provider, chain_id):
        if isinstance(signer_or_provider, LocalAccount):
            provider = None

        elif isinstance(signer_or_provider, Account):
            provider = None

        elif isinstance(signer_or_provider, SignerOrProvider):
            provider = signer_or_provider.provider

        elif isinstance(signer_or_provider, Web3):
            provider = signer_or_provider

        else:
            provider = None

        if provider is None:
            raise MissingProviderArbSdkError(signer_or_provider)

        provider_chain_id = provider.eth.chain_id
        if provider_chain_id != chain_id:
            raise ArbSdkError(
                f"Signer/provider chain id: {provider_chain_id} does not match provided chain id: {chain_id}."
            )
        else:
            return True
