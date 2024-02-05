from abc import ABC, abstractmethod

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import l1_networks
from src.lib.data_entities.signer_or_provider import SignerProviderUtils


class AssetBridger(ABC):
    def __init__(self, l2_network):
        self.l2_network = l2_network
        self.l1_network = l1_networks.get(l2_network.partner_chain_id)
        if not self.l1_network:
            raise ArbSdkError(f"Unknown l1 network chain id: {l2_network.partner_chain_id}")

    async def check_l1_network(self, sop):
        await SignerProviderUtils.check_network_matches(sop, self.l1_network.chain_id)

    async def check_l2_network(self, sop):
        await SignerProviderUtils.check_network_matches(sop, self.l2_network.chain_id)

    @abstractmethod
    async def deposit(self, params):
        pass

    @abstractmethod
    async def withdraw(self, params):
        pass
