class ArbSdkError(Exception):
    """
    Base class for errors originating in the Arbitrum SDK.
    Can optionally include an 'inner' exception to represent the original cause.
    """

    def __init__(self, message: str, inner: Exception = None):
        """
        :param message: The error message.
        :param inner: (Optional) Another exception that caused this error to be raised.
        """
        super().__init__(message)
        self.inner = inner

        # Build a custom 'stack' attribute if there's an inner exception
        if inner is not None:
            # Using repr(inner) or str(inner) to include the inner's message
            # This isn't standard Python for building a 'stack', but parallels TS code.
            self.stack = f"{message}\nCaused By: {repr(inner)}"
        else:
            self.stack = message

    def __str__(self):
        """
        Return the main error message plus any appended cause info.
        """
        return self.stack


class MissingProviderArbSdkError(ArbSdkError):
    """
    Thrown when a signer does not have a connected provider but one is required.
    """

    def __init__(self, signer_name: str):
        """
        :param signer_name: The name or identifier of the signer that lacks a provider.
        """
        super().__init__(
            f"{signer_name} does not have a connected provider and one is required."
        )
