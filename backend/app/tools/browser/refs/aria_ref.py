"""ARIA Reference Implementation

Provides ARIA attribute-based element references.
Uses aria-label, aria-role, and other ARIA attributes for selection.
"""
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import Page, Locator

from .base import BaseRef


@dataclass
class AriaRef(BaseRef):
    """ARIA attribute-based element reference

    Uses ARIA attributes for element selection.

    Attributes:
        element_id: Unique identifier (e.g., "aria:e1", "aria:e2")
        aria_label: aria-label attribute value
        aria_role: role attribute value (ARIA role)

    Example:
        # Create ARIA reference
        ref = AriaRef(element_id="aria:e1", aria_label="Close", aria_role="button")
        locator = ref.to_locator(page)
        locator.click()

        # String representation
        str(ref)  # "[aria:e1] role=button | label=\"Close\""
    """
    aria_label: Optional[str] = None
    aria_role: Optional[str] = None

    def to_locator(self, page: Page) -> Locator:
        """Convert to Playwright Locator using CSS selectors

        Args:
            page: Playwright Page instance

        Returns:
            Playwright Locator object
        """
        selectors = []

        # Build selector from ARIA attributes
        if self.aria_role:
            selectors.append(f"[role=\"{self.aria_role}\"]")
        if self.aria_label:
            selectors.append(f"[aria-label=\"{self.aria_label}\"]")

        if not selectors:
            # Fallback to element ID if no ARIA attributes
            return page.locator(f"#{self.element_id.replace('aria:', '')}")

        selector = "".join(selectors)
        locator = page.locator(selector)
        return locator

    def __str__(self) -> str:
        """String representation for LLM consumption

        Returns:
            Format: [aria:e1] role=button | label="Close"
        """
        parts = [self.element_id]
        if self.aria_role:
            parts.append(f"role={self.aria_role}")
        if self.aria_label:
            parts.append(f"label=\"{self.aria_label}\"")
        return "[" + " | ".join(parts) + "]"

    @classmethod
    def from_element(cls, element_id: str, element) -> 'AriaRef':
        """Create AriaRef from Playwright ElementHandle

        Args:
            element_id: Reference ID (e.g., "aria:e1")
            element: Playwright ElementHandle

        Returns:
            AriaRef instance
        """
        # Get ARIA attributes
        aria_label = element.evaluate("el => el.getAttribute('aria-label')")
        aria_role = element.evaluate("el => el.getAttribute('role')")

        return cls(
            element_id=element_id,
            aria_label=aria_label,
            aria_role=aria_role
        )
