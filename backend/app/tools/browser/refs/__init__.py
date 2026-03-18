"""Smart Reference System for Browser Tool

Provides intelligent element reference strategies:
- RoleRef: Semantic role-based references (button, textbox, link, etc.)
- AriaRef: ARIA attribute-based references
- CssRef: CSS selector references (backward compatibility)
- RefResolver: Unified reference parser and resolver
"""

from .base import BaseRef
from .role_ref import RoleRef
from .aria_ref import AriaRef
from .css_ref import CssRef
from .resolver import RefResolver

__all__ = [
    "BaseRef",
    "RoleRef",
    "AriaRef",
    "CssRef",
    "RefResolver",
]
