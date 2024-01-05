# def snake_to_camel(name):
#     # Special cases where the conversion isn't straightforward
#     special_cases = {"id": "ID", "ids": "IDs"}
#     components = name.split('_')
#     # Convert the first component as is, then title-case the remaining components
#     camel_case_name = components[0] + ''.join(special_cases.get(x, x.title()) for x in components[1:])
#     return camel_case_name


# class CamelSnakeCaseMixin:
#     def __getitem__(self, key):
#         return self.__getattr__(key)

#     def __getattr__(self, name):
#         # Try to fetch the attribute as is (for camelCase or any other case)
#         try:
#             return super().__getattribute__(name)
#         except AttributeError:
#             pass
        
#         # Convert snake_case to camelCase and try again
#         camel_case_name = snake_to_camel(name)
#         try:
#             return super().__getattribute__(camel_case_name)
#         except AttributeError:
#             pass

#         # If not found, raise AttributeError
#         raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

#     def __setattr__(self, name, value):
#         # Ensure attributes are stored in camelCase
#         if '_' in name:
#             name = snake_to_camel(name)
        
#         super().__setattr__(name, value)


# class Network(CamelSnakeCaseMixin):
#     def __init__(self, chainID, name, explorerUrl, isCustom, gif=None):
#         self.chainID = chainID
#         self.name = name
#         self.explorerUrl = explorerUrl
#         self.isCustom = isCustom
#         self.gif = gif


# class L1Network(Network):
#     def __init__(self, partnerChainIDs, blockTime, isArbitrum, **kwargs):
#         super().__init__(**kwargs)
#         self.partnerChainIDs = partnerChainIDs
#         self.blockTime = blockTime
#         self.isArbitrum = isArbitrum


# class L2Network(Network):
#     def __init__(
#         self,
#         tokenBridge,
#         ethBridge,
#         partnerChainID,
#         isArbitrum,
#         confirmPeriodBlocks,
#         retryableLifetimeSeconds,
#         nitroGenesisBlock,
#         nitroGenesisL1Block,
#         depositTimeout,
#         **kwargs,
#     ):
#         super().__init__(**kwargs)
#         self.tokenBridge = tokenBridge
#         self.ethBridge = ethBridge
#         self.partnerChainID = partnerChainID
#         self.isArbitrum = isArbitrum
#         self.confirmPeriodBlocks = confirmPeriodBlocks
#         self.retryableLifetimeSeconds = retryableLifetimeSeconds
#         self.nitroGenesisBlock = nitroGenesisBlock
#         self.nitroGenesisL1Block = nitroGenesisL1Block
#         self.depositTimeout = depositTimeout


# x = L2Network(
#     tokenBridge=None,
#     ethBridge=None,
#     partnerChainID=123,
#     isArbitrum=True,
#     confirmPeriodBlocks=123,
#     retryableLifetimeSeconds=123,
#     nitroGenesisBlock=123,
#     nitroGenesisL1Block=123,
#     depositTimeout=123,
#     chainID=123,
#     name='ArbLocal',
#     explorerUrl='',
#     isCustom=True,
# )

# print(x.partnerChainID)  # Access by camelCase attribute
# print(x['partnerChainID'])  # Access by camelCase key

# print(x.partner_chain_id)  # Access by camelCase attribute
# print(x['partner_chain_id'])  # Access by camelCase key
