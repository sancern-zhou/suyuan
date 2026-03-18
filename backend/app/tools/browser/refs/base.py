"""Base Reference Class

Abstract base class for all reference types.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import Page, Locator


@dataclass
class BaseRef(ABC):
    """Base class for element references

    Attributes:
        element_id: Unique identifier (e.g., "e1", "e2", "aria:e1")
    """
    element_id: str

    @abstractmethod
    def to_locator(self, page: Page) -> Locator:
        """Convert reference to Playwright Locator

        Args:
            page: Playwright Page instance

        Returns:
            Playwright Locator object
        """
        pass

    @abstractmethod
    def __str__(self) -> str:
        """String representation for LLM consumption

        Returns:
            Human-readable reference string
        """
        pass

    def with_index(self, n: int) -> 'BaseRef':
        """Create a new reference with index (returns self for compatibility)

        Args:
            n: Index (0-based)

        Returns:
            Self for compatibility
        """
        return self
