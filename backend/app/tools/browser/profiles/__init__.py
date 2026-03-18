"""Profile Management System

Provides multi-user browser profile management for session isolation.
Supports 10-20 concurrent profiles with independent data directories.
"""

from .manager import ProfileManager
from .config import ProfileConfig
from .driver import ProfileDriver

__all__ = ["ProfileManager", "ProfileConfig", "ProfileDriver"]
