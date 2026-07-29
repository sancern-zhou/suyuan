"""Company gateway authentication support."""

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .identity_cache import IdentityCache
from .models import CurrentUser
from .platform_client import PlatformAuthClient
from .service import AuthenticationService

__all__ = [
    "AuthenticationRejected",
    "AuthenticationUnavailable",
    "AuthenticationService",
    "CurrentUser",
    "IdentityCache",
    "PlatformAuthClient",
]
