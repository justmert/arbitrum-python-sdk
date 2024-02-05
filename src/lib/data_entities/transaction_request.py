from src.lib.utils.lib import is_defined


class L1ToL2MessageParams:
    pass


class L1ToL2MessageGasParams:
    pass


class L1ToL2TransactionRequest:
    def __init__(self, tx_request, retryable_data):
        self.tx_request = tx_request
        self.retryable_data = retryable_data

    async def is_valid(self):
        pass


class L2ToL1TransactionRequest:
    def __init__(self, tx_request, estimate_l1_gas_limit):
        self.tx_request = tx_request
        self.estimate_l1_gas_limit = estimate_l1_gas_limit


def is_l1_to_l2_transaction_request(possible_request):
    return is_defined(possible_request.get("txRequest", None))


def is_l2_to_l1_transaction_request(possible_request):
    return is_defined(possible_request.get("txRequest", None))
