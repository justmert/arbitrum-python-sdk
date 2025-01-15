import traceback
from typing import Optional


class ArbSdkError(Exception):
    """Base class for errors originating in the Arbitrum SDK.

    This class serves as the root exception type for all Arbitrum SDK-specific errors.
    It provides support for wrapping other exceptions to maintain the error chain and
    context, similar to the TypeScript implementation.

    Attributes:
        message (str): The error message
        inner (Optional[Exception]): The underlying exception that caused this error
        stack (str): A string containing this error's message and optionally the inner
            exception's stack trace
    """

    def __init__(self, message: str, inner: Optional[Exception] = None) -> None:
        """Initialize an ArbSdkError.

        Args:
            message: A descriptive error message
            inner: Optional exception that caused this error. If provided, its
                stack trace will be included in this error's stack trace.
        """
        super().__init__(message)
        self.message = message
        self.inner = inner

        # Build the stack trace string
        if inner is not None:
            # Get the inner exception's formatted stack trace
            inner_stack = "".join(traceback.format_exception(type(inner), inner, inner.__traceback__))
            self.stack = f"{message}\nCaused By: {inner_stack}"
        else:
            self.stack = message

    def __str__(self) -> str:
        """Get the complete error message including any inner exception details.

        Returns:
            A string containing this error's message and any inner exception details
        """
        return self.stack


class MissingProviderArbSdkError(ArbSdkError):
    """Error raised when a signer lacks a required provider connection.

    This error is thrown when attempting to use a signer that doesn't have a
    connected provider, but the operation requires one. This typically happens
    when trying to execute transactions or make contract calls.

    Attributes:
        signer_name (str): The name/identifier of the signer missing a provider
    """

    def __init__(self, signer_name: str) -> None:
        """Initialize a MissingProviderArbSdkError.

        Args:
            signer_name: Identifier for the signer that lacks a provider
        """
        self.signer_name = signer_name
        super().__init__(f"{signer_name} does not have a connected provider and one is required.")
