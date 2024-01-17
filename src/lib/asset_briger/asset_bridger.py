from abc import ABC, abstractmethod
from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import L2Network, l1_networks, L1Network
from src.lib.data_entities.signer_or_provider import SignerProviderUtils

class AssetBridger(ABC):
    def __init__(self, l2_network: L2Network):
        self.l2_network = l2_network
        # print("l1_netowkrs", l1_networks)
        self.l1_network = l1_networks.get(l2_network.partner_chain_id)        
        # print('l1_network instance', type(self.l1_network))
        if not self.l1_network:
            raise ArbSdkError(f"Unknown l1 network chain id: {l2_network.partner_chain_id}")

    async def check_l1_network(self, sop) -> None:
        await SignerProviderUtils.check_network_matches(sop, self.l1_network.chain_id)

    async def check_l2_network(self, sop) -> None:
        await SignerProviderUtils.check_network_matches(sop, self.l2_network.chain_id)

    @abstractmethod
    async def deposit(self, params):
        pass

    @abstractmethod
    async def withdraw(self, params):
        pass
