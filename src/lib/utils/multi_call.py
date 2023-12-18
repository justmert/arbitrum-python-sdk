import json
from web3 import Web3
from web3.contract import Contract
from src.lib.data_entities.networks import l1_networks, l2_networks
from src.lib.data_entities.errors import ArbSdkError


class MultiCaller:
    def __init__(self, provider, address):
        self.provider = provider
        self.address = address

    @staticmethod
    async def from_provider(provider: Web3):
        chain_id = await provider.eth.chain_id

        # Determine whether the network is L1 or L2 and find the network data
        l2_network = l2_networks.get(chain_id)
        l1_network = l1_networks.get(chain_id) if not l2_network else None

        if not l2_network and not l1_network:
            raise ArbSdkError(f"Unexpected network id: {chain_id}. Ensure that chain {chain_id} has been added as a network.")

        # Find the multicall address based on the network
        if l1_network:
            partner_chain_id = l1_network['partnerChainIDs'][0]
            first_l2 = l2_networks.get(partner_chain_id)
            if not first_l2:
                raise ArbSdkError(f"No partner chain found for L1 network: {chain_id}. Partner chain IDs: {l1_network['partnerChainIDs']}")
            multi_call_addr = first_l2['tokenBridge']['l1MultiCall']
        else:
            multi_call_addr = l2_network['tokenBridge']['l2Multicall']

        return MultiCaller(provider, multi_call_addr)

    def get_block_number_input(self):
        with open('path/to/Multicall2.json', 'r') as file:
            contract_data = json.load(file)
            abi = contract_data['abi']
            contract = self.provider.eth.contract(address=self.address, abi=abi)

        return {
            "target_addr": self.address,
            "encoder": lambda: contract.encodeABI(fn_name='getBlockNumber'),
            "decoder": lambda return_data: contract.decode_function_input('getBlockNumber', return_data)[1]
        }

    def get_current_block_timestamp_input(self):
        with open('path/to/Multicall2.json', 'r') as file:
            contract_data = json.load(file)
            abi = contract_data['abi']
            contract = self.provider.eth.contract(address=self.address, abi=abi)

        return {
            "target_addr": self.address,
            "encoder": lambda: contract.encodeABI(fn_name='getCurrentBlockTimestamp'),
            "decoder": lambda return_data: contract.decode_function_input('getCurrentBlockTimestamp', return_data)[1]
        }

    async def multi_call(self, params, require_success=False):
        with open('path/to/Multicall2.json', 'r') as file:
            contract_data = json.load(file)
            abi = contract_data['abi']
            contract = self.provider.eth.contract(address=self.address, abi=abi)

        args = [{'target': p['target_addr'], 'callData': p['encoder']()} for p in params]
        outputs = contract.functions.tryAggregate(require_success, args).call()

        return [p['decoder'](output['returnData']) if output['success'] else None for output, p in zip(outputs, params)]

    async def get_token_data(self, erc20_addresses, options=None):
        if options is None:
            options = {'name': True}

        # Load ERC20 contract ABI
        with open('path/to/ERC20.json', 'r') as file:
            erc20_abi = json.load(file)['abi']
        
        erc20_contract = self.provider.eth.contract(abi=erc20_abi)

        inputs = []
        for address in erc20_addresses:
            if options.get('balanceOf'):
                account = options['balanceOf']['account']
                inputs.append(self._create_call_input(address, erc20_contract, 'balanceOf', [account]))

            if options.get('allowance'):
                owner = options['allowance']['owner']
                spender = options['allowance']['spender']
                inputs.append(self._create_call_input(address, erc20_contract, 'allowance', [owner, spender]))

            if options.get('symbol'):
                inputs.append(self._create_call_input(address, erc20_contract, 'symbol', []))

            if options.get('decimals'):
                inputs.append(self._create_call_input(address, erc20_contract, 'decimals', []))

            if options.get('name'):
                inputs.append(self._create_call_input(address, erc20_contract, 'name', []))

        # Execute multicall
        results = await self.multi_call(inputs)

        # Parse results into structured format
        token_data = []
        for i in range(0, len(results), len(options)):
            token_info = {}
            if options.get('balanceOf'):
                token_info['balance'] = results[i]
                i += 1
            if options.get('allowance'):
                token_info['allowance'] = results[i]
                i += 1
            if options.get('symbol'):
                token_info['symbol'] = results[i]
                i += 1
            if options.get('decimals'):
                token_info['decimals'] = results[i]
                i += 1
            if options.get('name'):
                token_info['name'] = results[i]
                i += 1
            token_data.append(token_info)

        return token_data

    def _create_call_input(self, address, contract, method, args):
        return {
            "target_addr": address,
            "encoder": lambda: contract.encodeABI(fn_name=method, args=args),
            "decoder": lambda return_data: contract.decode_function_input(method, return_data)[1]
        }
