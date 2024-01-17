from web3 import Web3
from web3.providers import BaseProvider
from eth_account.signers.local import LocalAccount
from .errors import ArbSdkError, MissingProviderArbSdkError
from web3.providers import BaseProvider
from eth_account.signers.local import LocalAccount
from typing import Union
# from src.lib.utils.lib import is_defined
from web3.middleware import geth_poa_middleware

class SignerProviderUtils:
    @staticmethod
    def is_signer(signer_or_provider):
        # In Web3.py, this can be a heuristic based on the existence of certain attributes
        return hasattr(signer_or_provider, 'sign') and hasattr(signer_or_provider, 'address')

    @staticmethod
    def get_provider(signer_or_provider):
        # if SignerProviderUtils.is_signer(signer_or_provider):
        #     return signer_or_provider.web3
        # elif isinstance(signer_or_provider, Web3):
        #     return signer_or_provider
        # else:
        #     return None
        return signer_or_provider


    @staticmethod
    def get_provider_or_throw(signer_or_provider):
        # provider = SignerProviderUtils.get_provider(signer_or_provider)
        # if not provider:
        #     raise MissingProviderArbSdkError('signerOrProvider')
        # return provider
        return signer_or_provider


    @staticmethod
    def signer_has_provider(signer):
        # in web3.py, signer is a LocalAccount, which doesn't have a web3 attribute
        # return web3_instance is not None and web3_instance.is_connected()
        return signer

    @staticmethod
    async def check_network_matches(signer_or_provider, chain_id):

        if isinstance(signer_or_provider, Web3):
            provider_chain_id = signer_or_provider.eth.chain_id
            if provider_chain_id != chain_id:
                raise ArbSdkError(f'Signer/provider chain id: {provider_chain_id} does not match provided chain id: {chain_id}.')
            else:
                print("chain id matches")
                
