"""Company gateway authentication support."""

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser
from .platform_client import PlatformAuthClient

__all__ = [
    "AuthenticationRejected",
    "AuthenticationUnavailable",
    "CurrentUser",
    "PlatformAuthClient",
]
