from web3 import Web3
from web3.providers import BaseProvider
from eth_account.signers.local import LocalAccount
from .errors import ArbSdkError, MissingProviderArbSdkError
from web3.providers import BaseProvider
from eth_account.signers.local import LocalAccount
from typing import Union

SignerOrProvider = Union[LocalAccount, BaseProvider]


class SignerProviderUtils:
    @staticmethod
    def is_signer(signer_or_provider):
        # return isinstance(signer_or_provider, LocalAccount)
        return True

    @staticmethod
    def get_provider(signer_or_provider):
        # if SignerProviderUtils.is_signer(signer_or_provider):
        #     return signer_or_provider.web3.provider
        # elif isinstance(signer_or_provider, BaseProvider):
        #     return signer_or_provider
        # else:
        #     return None
        return signer_or_provider

    @staticmethod
    def get_provider_or_throw(signer_or_provider):
        # provider = SignerProviderUtils.get_provider(signer_or_provider)
        # if not provider:
        #     raise MissingProviderArbSdkError('signer_or_provider')
        return signer_or_provider

    @staticmethod
    def signer_has_provider(signer):
        # return SignerProviderUtils.is_signer(signer) and signer.web3 is not None
        return signer

    @staticmethod
    async def check_network_matches(signer_or_provider, chain_id):
        # provider = SignerProviderUtils.get_provider(signer_or_provider)
        # if not provider:
        #     raise MissingProviderArbSdkError('signer_or_provider')

        # provider_chain_id = await Web3(provider).eth.chain_id
        # if provider_chain_id != chain_id:
        #     raise ArbSdkError(f'Signer/provider chain id: {provider_chain_id} does not match provided chain id: {chain_id}.')

        if isinstance(signer_or_provider, Web3):
            if signer_or_provider.eth.chain_id != chain_id:
                raise ArbSdkError(f'Signer/provider chain id: {signer_or_provider.eth.chain_id} does not match provided chain id: {chain_id}.')
                
