"""Reference Resolver - Convert ref IDs to Playwright Locators

类似 MoltBot 的 refLocator 实现，自动将 ref ID 转换为可用的 locator。
"""
import structlog
import re
from typing import Dict, Optional
from playwright.sync_api import Page, Locator

from .role_ref import RoleRef

logger = structlog.get_logger()


class RefResolver:
    """Resolver for element references

    Stores refs from snapshot and converts ref IDs to Playwright locators.

    Example:
        resolver = RefResolver()
        resolver.set_refs({"e1": {"role": "textbox", "name": "用户名"}})
        locator = resolver.resolve(page, "e1")  # Returns get_by_role("textbox", name="用户名")
    """

    def __init__(self):
        self._refs: Dict[str, dict] = {}

    def set_refs(self, refs: Dict[str, dict]):
        """Set refs from snapshot

        Args:
            refs: Dictionary from snapshot result
        """
        self._refs = refs.copy()
        logger.info("[REF_RESOLVER] Refs loaded", count=len(refs))

    def resolve(self, page: Page, ref: str) -> Locator:
        """Resolve ref ID to Playwright Locator

        Args:
            page: Playwright Page instance
            ref: Reference ID (e.g., "e1", "e12")

        Returns:
            Playwright Locator object

        Raises:
            ValueError: If ref not found in stored refs
        """
        # Normalize ref (remove @ or ref= prefix)
        normalized = ref.lstrip('@')
        if normalized.startswith('ref='):
            normalized = normalized[4:]

        # Check if it's a standard ref (e1, e2, etc.)
        if not re.match(r'^e\d+$', normalized):
            raise ValueError(f"Invalid ref format: {ref}. Expected e1, e2, etc.")

        # Get ref info
        ref_info = self._refs.get(normalized)
        if not ref_info:
            available_refs = list(self._refs.keys())[:10]  # Show first 10
            raise ValueError(
                f"Unknown ref '{ref}'. "
                f"Run a new snapshot and use a ref from that snapshot. "
                f"Available refs: {available_refs}..."
            )

        # Create locator based on ref info
        role = ref_info.get("role")
        name = ref_info.get("name")
        nth = ref_info.get("nth", 0)

        if not role:
            raise ValueError(f"Ref '{ref}' missing required 'role' field")

        # Build get_by_role arguments
        kwargs = {}
        if name:
            kwargs['name'] = name
            kwargs['exact'] = True

        # Get locator
        locator = page.get_by_role(role, **kwargs)

        # Apply nth if specified
        if nth and nth > 0:
            locator = locator.nth(nth)

        logger.info(
            "[REF_RESOLVER] Ref resolved",
            ref=ref,
            role=role,
            name=name,
            nth=nth
        )

        return locator

    def has_ref(self, ref: str) -> bool:
        """Check if ref exists in stored refs

        Args:
            ref: Reference ID

        Returns:
            True if ref exists
        """
        normalized = ref.lstrip('@')
        if normalized.startswith('ref='):
            normalized = normalized[4:]
        return normalized in self._refs

    def get_ref_info(self, ref: str) -> Optional[dict]:
        """Get stored ref information

        Args:
            ref: Reference ID



        Returns:
            Ref info dictionary or None
        """
        normalized = ref.lstrip('@')
        if normalized.startswith('ref='):
            normalized = normalized[4:]
        return self._refs.get(normalized)


# Global resolver instance (for session-based refs)
_global_resolver = RefResolver()


def get_global_resolver() -> RefResolver:
    """Get the global ref resolver instance

    Returns:
        RefResolver instance
    """
    return _global_resolver


def set_global_refs(refs: Dict[str, dict]):
    """Set refs in the global resolver

    Args:
        refs: Reference dictionary from snapshot
    """
    _global_resolver.set_refs(refs)
