from typing import Any, Dict, List, Optional, Union

from web3 import Web3

from src.lib.data_entities.errors import ArbSdkError
from src.lib.data_entities.networks import get_multicall_address
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.utils.arb_provider import ArbitrumProvider
from src.lib.utils.helper import load_contract

class MultiCaller:
    """
    Python equivalent of the TypeScript `MultiCaller` class. 
    Uses a 'Multicall2' contract to perform batch calls on chain 
    and decode the results.
    """

    def __init__(self, provider: Union[Web3, SignerOrProvider, ArbitrumProvider], address: str):
        """
        :param provider: A raw Web3 instance, SignerOrProvider, or ArbitrumProvider
        :param address: The address of the deployed Multicall2 contract
        """
        if isinstance(provider, Web3):
            self.provider = provider
        elif isinstance(provider, SignerOrProvider):
            if provider.provider is None:
                raise ArbSdkError("No underlying provider found in SignerOrProvider.")
            self.provider = provider.provider
        elif isinstance(provider, ArbitrumProvider):
            self.provider = provider.provider
        else:
            raise ArbSdkError("Invalid provider type for MultiCaller.")

        self.address = address

    @staticmethod
    async def from_provider(provider: Union[Web3, SignerOrProvider, ArbitrumProvider]) -> "MultiCaller":
        """
        Creates a MultiCaller by looking up the Multicall2 address 
        for the chain to which `provider` is connected.

        :param provider: A Web3, SignerOrProvider, or ArbitrumProvider
        :return: A new MultiCaller instance
        """
        multicall_addr = await get_multicall_address(provider)
        return MultiCaller(provider, multicall_addr)

    def get_block_number_input(self) -> Dict[str, Any]:
        """
        Returns a structured call input for retrieving the current block number 
        from Multicall2.

        :return: A dict with 'targetAddr', 'encoder', 'decoder'
        """
        contract = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )

        return {
            "targetAddr": self.address,
            "encoder": lambda: contract.encodeABI(fn_name="getBlockNumber"),
            "decoder": lambda return_data: contract.decode_function_input("getBlockNumber", return_data)[1],
        }

    def get_current_block_timestamp_input(self) -> Dict[str, Any]:
        """
        Returns a structured call input for retrieving the current block timestamp 
        from Multicall2.

        :return: A dict with 'targetAddr', 'encoder', 'decoder'
        """
        contract = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )
        return {
            "targetAddr": self.address,
            "encoder": lambda: contract.encodeABI(fn_name="getCurrentBlockTimestamp"),
            "decoder": lambda return_data: contract.decode_function_input("getCurrentBlockTimestamp", return_data)[1],
        }

    async def multi_call(self, params: List[Dict[str, Any]], require_success: bool = False) -> List[Any]:
        """
        Execute a batch of calls against the multicall contract. 
        Each item in 'params' should contain:
         - 'targetAddr': The address to call
         - 'encoder': A function returning the encoded call data
         - 'decoder': A function to decode the returned data

        :param params: A list of dict objects describing how to encode/decode each call
        :param require_success: If True, will revert if any sub-call fails
        :return: A list of decoded results, or None if the call failed (when require_success = False)
        """
        multi_call_contract = load_contract(
            provider=self.provider,
            contract_name="Multicall2",
            address=self.address,
            is_classic=True,
        )

        # Build the array of calls
        calls = []
        for p in params:
            calls.append({
                "target": p["targetAddr"],
                "callData": p["encoder"]()
            })

        # tryAggregate(bool requireSuccess, Call[] calls) returns (bool success, bytes returnData)[]
        outputs = multi_call_contract.functions.tryAggregate(
            require_success,
            calls
        ).call()

        decoded_results = []
        for ((success, return_data), p) in zip(outputs, params):
            if success and return_data and return_data != "0x":
                decoded_results.append(p["decoder"](return_data))
            else:
                # If it fails or empty, yield None
                decoded_results.append(None)
        return decoded_results

    async def get_token_data(self, erc20_addresses: List[str], options: dict = None) -> List[dict]:
        """
        Retrieves token info (balanceOf, allowance, symbol, decimals, name) 
        for each address in erc20_addresses, according to 'options'.

        :param erc20_addresses: List of token addresses
        :param options: A dictionary specifying which fields to retrieve, e.g. 
            { "balanceOf": { "account": "0x..." }, "allowance": {"owner": "0x...","spender": "0x..."},"symbol":True,"decimals":True,"name":True }
        :return: A list of dicts where each dict has the results for that token in the same order as erc20_addresses
        """
        if options is None:
            # default to name
            options = {"name": True}

        # We'll gather input calls, then decode them in batch
        contract = load_contract(self.provider, "ERC20", is_classic=True)
        inputs: List[Dict[str, Any]] = []

        # For each token, for each option we want, create a call
        for address in erc20_addresses:
            # balanceOf
            if "balanceOf" in options:
                account = options["balanceOf"]["account"]
                inputs.append(self._make_call_input(contract, address, "balanceOf", [account]))
            # allowance
            if "allowance" in options:
                owner = options["allowance"]["owner"]
                spender = options["allowance"]["spender"]
                inputs.append(self._make_call_input(contract, address, "allowance", [owner, spender]))
            # symbol
            if options.get("symbol"):
                inputs.append(self._make_call_input(contract, address, "symbol", []))
            # decimals
            if options.get("decimals"):
                inputs.append(self._make_call_input(contract, address, "decimals", []))
            # name
            if options.get("name"):
                inputs.append(self._make_call_input(contract, address, "name", []))

        results = await self.multi_call(inputs)

        # Re-chunk results by token
        token_info_list = []
        idx = 0
        for _ in erc20_addresses:
            token_info = {}
            if "balanceOf" in options:
                token_info["balance"] = results[idx]; idx += 1
            if "allowance" in options:
                token_info["allowance"] = results[idx]; idx += 1
            if options.get("symbol"):
                token_info["symbol"] = results[idx]; idx += 1
            if options.get("decimals"):
                token_info["decimals"] = results[idx]; idx += 1
            if options.get("name"):
                token_info["name"] = results[idx]; idx += 1
            token_info_list.append(token_info)

        return token_info_list

    def _make_call_input(
        self,
        contract,
        target_addr: str,
        method_name: str,
        args: List[Any]
    ) -> Dict[str, Any]:
        """
        Helper to build a single call input dict for multiCall.
        """
        return {
            "targetAddr": target_addr,
            "encoder": lambda: contract.encodeABI(fn_name=method_name, args=args),
            "decoder": lambda return_data: contract.decode_function_input(method_name, return_data)[1]
        }
