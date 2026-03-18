"""Unified Reference Resolver

Parses and resolves various reference formats into Playwright Locators.
Supports Role refs, ARIA refs, and CSS refs with automatic format detection.
"""
import re
import structlog
from typing import Union, Dict, Optional
from playwright.sync_api import Page, Locator

from .base import BaseRef
from .role_ref import RoleRef
from .aria_ref import AriaRef
from .css_ref import CssRef

logger = structlog.get_logger()


class RefResolver:
    """Unified reference parser and resolver

    Supports multiple reference formats:
    - Role refs: e1, e2, e3 (semantic role-based)
    - ARIA refs: aria:e1, aria:e2 (ARIA attribute-based)
    - CSS refs: #id, .class, tag[attr=value] (backward compatibility)
    """

    # Reference pattern matching
    ROLE_REF_PATTERN = re.compile(r'^e(\d+)$')  # e1, e2, e3...
    ARIA_REF_PATTERN = re.compile(r'^aria:e(\d+)$')  # aria:e1, aria:e2...
    CSS_SELECTOR_PATTERNS = [
        re.compile(r'^#[\w-]+$'),  # ID: #submit-btn
        re.compile(r'^\.[\w-]+$'),  # Class: .btn-primary
        re.compile(r'^[\w-]+\[.+\]$'),  # Attribute: input[type="submit"]
        re.compile(r'^[\w-]+:has-text\(.+\)$'),  # Text: button:has-text("Login")
        re.compile(r'^[\w-]+$'),  # Tag: button, input, a
    ]

    @staticmethod
    def resolve(page: Page, ref: str, refs_context: Optional[Dict] = None) -> Locator:
        """Parse and resolve reference to Playwright Locator

        Args:
            page: Playwright Page instance
            ref: Reference string (e1, aria:e1, #id, .class, etc.)
            refs_context: Context from snapshot containing ref definitions

        Returns:
            Playwright Locator object

        Raises:
            ValueError: If reference format is invalid

        Example:
            # Role reference (requires context)
            locator = RefResolver.resolve(page, "e1", refs_context)
            # ARIA reference (requires context)
            locator = RefResolver.resolve(page, "aria:e1", refs_context)
            # CSS reference (direct)
            locator = RefResolver.resolve(page, "#submit-btn")
        """
        logger.info("[REF_RESOLVER] Resolving reference", ref=ref, has_context=refs_context is not None)

        # Try Role reference first
        role_match = RefResolver.ROLE_REF_PATTERN.match(ref)
        if role_match:
            return RefResolver._resolve_role_ref(page, ref, refs_context)

        # Try ARIA reference
        aria_match = RefResolver.ARIA_REF_PATTERN.match(ref)
        if aria_match:
            return RefResolver._resolve_aria_ref(page, ref, refs_context)

        # Try CSS selector (fallback)
        return RefResolver._resolve_css_ref(page, ref)

    @staticmethod
    def _resolve_role_ref(page: Page, ref: str, refs_context: Optional[Dict]) -> Locator:
        """Resolve Role reference using context

        Args:
            page: Playwright Page instance
            ref: Role reference (e1, e2, etc.)
            refs_context: Context from snapshot

        Returns:
            Playwright Locator
        """
        if not refs_context or ref not in refs_context:
            logger.warning("[REF_RESOLVER] Role ref not found in context", ref=ref)
            # Fallback: try to find by text content or ID
            return page.locator(f"[data-ref=\"{ref}\"]").or_(page.locator(f"#{ref}"))

        ctx = refs_context[ref]
        role_ref = RoleRef(
            element_id=ref,
            role=ctx.get("role", "generic"),
            name=ctx.get("name")
        )

        logger.info(
            "[REF_RESOLVER] Resolved role ref",
            ref=ref,
            role=role_ref.role,
            name=role_ref.name
        )

        return role_ref.to_locator(page)

    @staticmethod
    def _resolve_aria_ref(page: Page, ref: str, refs_context: Optional[Dict]) -> Locator:
        """Resolve ARIA reference using context

        Args:
            page: Playwright Page instance
            ref: ARIA reference (aria:e1, aria:e2, etc.)
            refs_context: Context from snapshot

        Returns:
            Playwright Locator
        """
        if not refs_context or ref not in refs_context:
            logger.warning("[REF_RESOLVER] ARIA ref not found in context", ref=ref)
            # Fallback: try as CSS selector
            return page.locator(f"#{ref.replace('aria:', '')}")

        ctx = refs_context[ref]
        aria_ref = AriaRef(
            element_id=ref,
            aria_label=ctx.get("aria_label"),
            aria_role=ctx.get("aria_role")
        )

        logger.info(
            "[REF_RESOLVER] Resolved ARIA ref",
            ref=ref,
            aria_role=aria_ref.aria_role,
            aria_label=aria_ref.aria_label
        )

        return aria_ref.to_locator(page)

    @staticmethod
    def _resolve_css_ref(page: Page, selector: str) -> Locator:
        """Resolve CSS selector reference

        Args:
            page: Playwright Page instance
            selector: CSS selector string

        Returns:
            Playwright Locator
        """
        logger.info("[REF_RESOLVER] Resolved as CSS selector", selector=selector)
        return page.locator(selector)

    @staticmethod
    def detect_ref_type(ref: str) -> str:
        """Detect reference type without resolving

        Args:
            ref: Reference string

        Returns:
            One of: "role", "aria", "css"
        """
        if RefResolver.ROLE_REF_PATTERN.match(ref):
            return "role"
        elif RefResolver.ARIA_REF_PATTERN.match(ref):
            return "aria"
        else:
            return "css"

    @staticmethod
    def validate_ref(ref: str) -> bool:
        """Validate reference format

        Args:
            ref: Reference string

        Returns:
            True if format is valid
        """
        ref_type = RefResolver.detect_ref_type(ref)

        if ref_type == "css":
            # Additional validation for CSS selectors
            for pattern in RefResolver.CSS_SELECTOR_PATTERNS:
                if pattern.match(ref):
                    return True
            return False

        return True
