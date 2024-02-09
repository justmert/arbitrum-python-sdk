from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import is_l1_network, l1_networks, l2_networks
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import load_contract


class MultiCaller:
    def __init__(self, provider, address):
        if isinstance(provider, Web3):
            self.provider = provider

        elif isinstance(provider, SignerOrProvider):
            self.provider = provider.provider

        elif isinstance(provider, ArbitrumProvider):
            provider = provider.provider

        else:
            raise ArbSdkError("Invalid provider type")

        self.address = address

    @staticmethod
    async def from_provider(provider):
        chain_id = provider.eth.chain_id

        l2_network = l2_networks.get(chain_id, None)
        l1_network = l1_networks.get(chain_id, None)

        network = l2_network or l1_network

        if not network:
            raise ArbSdkError(
                f"Unexpected network id: {chain_id}. Ensure that chain {chain_id} has been added as a network."
            )

        if is_l1_network(network):
            first_l2 = l2_networks[network.partner_chain_ids[0]]
            if not first_l2:
                raise ArbSdkError(
                    f"No partner chain found for L1 network: {network.chain_id}. Partner chain IDs: {l1_network.partner_chain_ids}"
                )

            multi_call_addr = first_l2.token_bridge.l1_multi_call
        else:
            multi_call_addr = network.token_bridge.l2_multi_call

        return MultiCaller(provider, multi_call_addr)

    def get_block_number_input(self):
        iface = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )
        return {
            "targetAddr": self.address,
            "encoder": lambda: iface.encodeABI(fn_name="getBlockNumber"),
            "decoder": lambda return_data: iface.decode_function_input("getBlockNumber", return_data)[1],
        }

    def get_current_block_timestamp_input(self):
        iface = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )

        return {
            "targetAddr": self.address,
            "encoder": lambda: iface.encodeABI(fn_name="getCurrentBlockTimestamp"),
            "decoder": lambda return_data: iface.decode_function_input("getCurrentBlockTimestamp", return_data)[1],
        }

    async def multi_call(self, params, require_success=False):
        multi_call_contract = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )

        args = [{"target": p["targetAddr"], "callData": p["encoder"]()} for p in params]

        outputs = multi_call_contract.functions.tryAggregate(require_success, args).call()

        return [p["decoder"](output["returnData"]) if output["success"] else None for output, p in zip(outputs, params)]

    async def get_token_data(self, erc20_addresses, defaulted_options=None):
        if defaulted_options is None:
            defaulted_options = {"name": True}

        erc20_iface = load_contract(provider=self.provider, contract_name="ERC20", is_classic=True)
        inputs = []
        for address in erc20_addresses:
            if defaulted_options.get("balanceOf"):
                account = defaulted_options["balanceOf"]["account"]
                inputs.append(self._create_call_input(address, erc20_iface, "balanceOf", [account]))

            if defaulted_options.get("allowance"):
                owner = defaulted_options["allowance"]["owner"]
                spender = defaulted_options["allowance"]["spender"]
                inputs.append(self._create_call_input(address, erc20_iface, "allowance", [owner, spender]))

            if defaulted_options.get("symbol"):
                inputs.append(self._create_call_input(address, erc20_iface, "symbol", []))

            if defaulted_options.get("decimals"):
                inputs.append(self._create_call_input(address, erc20_iface, "decimals", []))

            if defaulted_options.get("name"):
                inputs.append(self._create_call_input(address, erc20_iface, "name", []))

        results = await self.multi_call(inputs)
        token_data = []
        for i in range(0, len(results), len(defaulted_options)):
            token_info = {}
            if defaulted_options.get("balanceOf"):
                token_info["balance"] = results[i]
                i += 1
            if defaulted_options.get("allowance"):
                token_info["allowance"] = results[i]
                i += 1
            if defaulted_options.get("symbol"):
                token_info["symbol"] = results[i]
                i += 1
            if defaulted_options.get("decimals"):
                token_info["decimals"] = results[i]
                i += 1
            if defaulted_options.get("name"):
                token_info["name"] = results[i]
                i += 1
            token_data.append(token_info)

        return token_data

    def _create_call_input(self, address, contract, method, args):
        return {
            "targetAddr": address,
            "encoder": lambda: contract.encodeABI(fn_name=method, args=args),
            "decoder": lambda return_data: contract.decode_function_input(method, return_data)[1],
        }
