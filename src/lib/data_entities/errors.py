class ArbSdkError(Exception):
    """
    Errors originating in Arbitrum SDK
    """

    def __init__(self, message, inner=None):
        super().__init__(message)
        self.inner = inner
        if inner:
            self.stack = f"{self.__str__()}\nCaused By: {inner.__str__()}"


class MissingProviderArbSdkError(ArbSdkError):
    """
    Thrown when a signer does not have a connected provider
    """

    def __init__(self, signer_name):
        super().__init__(
            f"{signer_name} does not have a connected provider and one is required."
        )
