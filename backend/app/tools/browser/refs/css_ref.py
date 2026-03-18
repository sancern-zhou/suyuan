"""CSS Reference Implementation

Provides CSS selector-based element references for backward compatibility.
"""
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import Page, Locator

from .base import BaseRef


@dataclass
class CssRef(BaseRef):
    """CSS selector-based element reference

    Uses standard CSS selectors for element selection.
    Provides backward compatibility with existing selector-based code.

    Attributes:
        element_id: Unique identifier or selector
        selector: CSS selector string

    Example:
        # Create CSS reference
        ref = CssRef(element_id="css:submit", selector="#submit-btn")
        locator = ref.to_locator(page)
        locator.click()
    """
    selector: str

    def to_locator(self, page: Page) -> Locator:
        """Convert to Playwright Locator using CSS selector

        Args:
            page: Playwright Page instance

        Returns:
            Playwright Locator object
        """
        locator = page.locator(self.selector)
        return locator

    def __str__(self) -> str:
        """String representation for LLM consumption

        Returns:
            Format: [css:submit] #submit-btn
        """
        return f"[{self.element_id}] {self.selector}"
