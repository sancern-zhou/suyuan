"""Focused authentication exceptions used at HTTP boundaries."""


class AuthenticationError(RuntimeError):
    """Base class for company authentication failures."""


class AuthenticationRejected(AuthenticationError):
    """The supplied company credential cannot establish an identity."""


class AuthenticationUnavailable(AuthenticationError):
    """The authentication infrastructure could not answer safely."""


class AuthenticationConfigurationError(AuthenticationError):
    """Authentication cannot start because required configuration is absent."""
