"""ARIA Formatter - ARIA-based Snapshot Format

Generates snapshots using ARIA attributes for element references.
"""
import structlog
from typing import Dict, List
from playwright.sync_api import Page

from ...refs.aria_ref import AriaRef

logger = structlog.get_logger()


class ARIAFormatter:
    """ARIA Format Snapshot Generator

    Creates ARIA attribute-based snapshots with:
    - ARIA labels and roles
    - aria:e1, aria:e2 reference format
    - Focus on accessibility attributes

    Example output:
        [aria:e1] role=button | label="Close"
        [aria:e2] role= textbox | label="Username"
    """

    # CSS selector for elements with ARIA attributes
    ARIA_SELECTOR = """
    [role], [aria-label], [aria-labelledby],
    [aria-describedby], [aria-hidden]
    """

    def format(
        self,
        page: Page,
        max_refs: int = 100,
        interactive_only: bool = False,
        depth: int = 10
    ) -> Dict:
        """Generate ARIA format snapshot

        Args:
            page: Playwright Page instance
            max_refs: Maximum number of refs to generate
            interactive_only: Only include interactive elements
            depth: DOM traversal depth (not used in current implementation)

        Returns:
            {
                "ok": True,
                "format": "aria",
                "snapshot": str,  # Formatted snapshot text
                "refs": {...},     # Reference context for resolver
                "stats": {...}     # Statistics
            }
        """
        refs = {}
        lines = []
        ref_count = 0

        try:
            # Get elements with ARIA attributes
            elements = page.query_selector_all(self.ARIA_SELECTOR)

            for element in elements:
                if ref_count >= max_refs:
                    break

                try:
                    # Create ARIA reference from element
                    ref_id = f"aria:e{ref_count + 1}"
                    aria_ref = AriaRef.from_element(ref_id, element)

                    # Skip elements without meaningful ARIA attributes
                    if not aria_ref.aria_label and not aria_ref.aria_role:
                        continue

                    # Store reference context
                    refs[ref_id] = {
                        "aria_label": aria_ref.aria_label,
                        "aria_role": aria_ref.aria_role,
                    }

                    # Format line
                    line = str(aria_ref)
                    lines.append(line)

                    ref_count += 1

                except Exception as e:
                    # Skip elements that can't be processed
                    logger.debug("[ARIA_FORMATTER] Skipping element", error=str(e))
                    continue

            snapshot_text = "\n".join(lines)

            # Calculate statistics
            stats = {
                "total_refs": ref_count,
                "with_label": sum(1 for r in refs.values() if r["aria_label"]),
                "with_role": sum(1 for r in refs.values() if r["aria_role"]),
                "lines": len(lines),
                "chars": len(snapshot_text)
            }

            logger.info(
                "[ARIA_FORMATTER] Snapshot generated",
                format="aria",
                total_refs=ref_count,
                with_label=stats["with_label"],
                with_role=stats["with_role"]
            )

            return {
                "ok": True,
                "format": "aria",
                "snapshot": snapshot_text,
                "refs": refs,
                "stats": stats
            }

        except Exception as e:
            logger.error("[ARIA_FORMATTER] Failed to generate snapshot", error=str(e))
            return {
                "ok": False,
                "format": "aria",
                "snapshot": "",
                "refs": {},
                "stats": {"error": str(e)}
            }
