def snake_to_camel(name):
    # Special cases where the conversion isn't straightforward
    special_cases = {"id": "ID", "ids": "IDs"}
    components = name.split('_')
    # Convert the first component as is, then title-case the remaining components
    camel_case_name = components[0] + ''.join(special_cases.get(x, x.title()) for x in components[1:])
    return camel_case_name


class CamelSnakeCaseMixin:
    def __getitem__(self, key):
        return self.__getattr__(key)

    def __getattr__(self, name):
        # Try to fetch the attribute as is (for camelCase or any other case)
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass
        
        # Convert snake_case to camelCase and try again
        camel_case_name = snake_to_camel(name)
        try:
            return super().__getattribute__(camel_case_name)
        except AttributeError:
            pass

        # If not found, raise AttributeError
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        # Ensure attributes are stored in camelCase
        if '_' in name:
            name = snake_to_camel(name)
        
        super().__setattr__(name, value)

    def to_dict(self):
        return {attr: self.convert_to_serializable(getattr(self, attr)) for attr in self.__dict__}


    def convert_to_serializable(self, value):
        # If the value is an instance of CamelSnakeCaseMixin, convert it to a dictionary
        if isinstance(value, CamelSnakeCaseMixin):
            return value.to_dict()
        # If the value is a list, apply this conversion to each element
        elif isinstance(value, list):
            return [self.convert_to_serializable(item) for item in value]
        # If the value is a dictionary, apply this conversion to each value
        elif isinstance(value, dict):
            return {key: self.convert_to_serializable(val) for key, val in value.items()}
    
        # elif isinstance(value, Contract):
        #     return value.address
        else:
            return value
        

class Test(CamelSnakeCaseMixin):
    def __init__(self, x):
        for key, value in x.items():
            setattr(self, key, value)
    


x = {
        'l1_signer': "aaa",
        'l2_signer': "aaa",
        'l1_network': "aaa",
        'l2_network': "aaa",
        'erc20_bridger': "aaa",
        'admin_erc20_bridger': "aaa",
        'eth_bridger': "aaa",
        'inbox_tools': "aaa",
        'l1_deployer': "aaa",
        'l2_deployer': "aaa",
        'l1_provider': "aaa",
        'l2_provider': "aaa",
        'l1_private_key': "aaa",
        'l2_private_key': "aaa",
    }



t = Test(x)
print(t.l1Signer)
print(t["l1Signer"])
print(t.l1_signer)