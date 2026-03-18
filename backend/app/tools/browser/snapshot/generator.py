"""Snapshot Generator - Unified Snapshot Generation

Provides unified interface for generating snapshots in LLM-optimized formats.

Note: text format has been removed. Use AI format for better LLM support.
"""
import structlog
from typing import Dict
from playwright.sync_api import Page

from .formatters.ai_formatter import AIFormatter
from .formatters.aria_formatter import ARIAFormatter

logger = structlog.get_logger()


class SnapshotGenerator:
    """Unified snapshot generator supporting LLM-optimized formats

    Supported formats:
    - ai: LLM-optimized format with role-based refs (default)
    - aria: ARIA attribute-based format

    Note: text format removed in v3.1 - use ai format instead
    """

    def __init__(self):
        self.ai_formatter = AIFormatter()
        self.aria_formatter = ARIAFormatter()

    def generate(
        self,
        page: Page,
        format: str = "ai",
        max_refs: int = 100,
        interactive_only: bool = False,
        depth: int = 10,
        compact: bool = False
    ) -> Dict:
        """Generate page snapshot in specified format

        Args:
            page: Playwright Page instance
            format: Snapshot format (ai/aria)
            max_refs: Maximum number of refs (default: 100)
            interactive_only: Only include interactive elements (default: False)
            depth: DOM traversal depth (default: 10)
            compact: Remove unnamed structural elements (default: False)

        Returns:
            {
                "ok": True,
                "format": str,
                "snapshot": str,
                "refs": dict,
                "stats": dict
            }

        Raises:
            ValueError: If format is not supported
        """
        logger.info(
            "[SNAPSHOT_GENERATOR] Generating snapshot",
            format=format,
            max_refs=max_refs,
            interactive_only=interactive_only,
            compact=compact
        )

        if format == "ai":
            return self.ai_formatter.format(page, max_refs, interactive_only, depth, compact)
        elif format == "aria":
            return self.aria_formatter.format(page, max_refs, interactive_only, depth)
        else:
            raise ValueError(
                f"Unsupported snapshot format: {format}. "
                f"Supported formats: ai, aria. "
                f"text format has been removed."
            )

    def get_supported_formats(self) -> list:
        """Get list of supported snapshot formats

        Returns:
            List of format names
        """
        return ["ai", "aria"]
