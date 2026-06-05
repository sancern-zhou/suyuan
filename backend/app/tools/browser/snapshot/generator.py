"""Snapshot Generator - Unified Snapshot Generation

Provides unified interface for generating snapshots in LLM-optimized formats.

Note: text format has been removed. Use AI format for better LLM support.
"""
import structlog
from typing import Dict
from playwright.sync_api import Page

from .formatters.ai_formatter import AIFormatter
from .formatters.aria_formatter import ARIAFormatter
from ..services.frame_target import resolve_frame

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
        compact: bool = False,
        include_frames: bool = True,
        frame_url: str = None,
        frame_name: str = None,
        frame_index: int = None
    ) -> Dict:
        """Generate page snapshot in specified format

        Args:
            page: Playwright Page instance
            format: Snapshot format (ai/aria)
            max_refs: Maximum number of refs (default: 100)
            interactive_only: Only include interactive elements (default: False)
            depth: DOM traversal depth (default: 10)
            compact: Remove unnamed structural elements (default: False)
            include_frames: Include all frames in AI snapshots by default
            frame_url: Target one frame by URL substring
            frame_name: Target one frame by name
            frame_index: Target one frame by index in page.frames

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
            if frame_url or frame_name or frame_index is not None:
                frame = resolve_frame(page, frame_url=frame_url, frame_name=frame_name, frame_index=frame_index)
                index = list(page.frames).index(frame)
                return self.ai_formatter.format(
                    frame,
                    max_refs=max_refs,
                    interactive_only=interactive_only,
                    depth=depth,
                    compact=compact,
                    ref_prefix=f"f{index}:",
                )

            if include_frames:
                return self._generate_ai_frames(page, max_refs, interactive_only, depth, compact)

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

    def _generate_ai_frames(
        self,
        page: Page,
        max_refs: int,
        interactive_only: bool,
        depth: int,
        compact: bool
    ) -> Dict:
        lines = []
        refs = {}
        total_stats = {
            "total_refs": 0,
            "interactive_refs": 0,
            "lines": 0,
            "chars": 0,
            "frames": 0,
        }

        remaining = max_refs
        for index, frame in enumerate(page.frames):
            if remaining <= 0:
                break

            frame_result = self.ai_formatter.format(
                frame,
                max_refs=remaining,
                interactive_only=interactive_only,
                depth=depth,
                compact=compact,
                ref_prefix=f"f{index}:",
            )
            frame_refs = frame_result.get("refs", {})
            if not frame_refs and not frame_result.get("snapshot"):
                continue

            lines.append(f"## Frame {index}: {getattr(frame, 'url', '')}")
            if frame_result.get("snapshot"):
                lines.append(frame_result["snapshot"])

            refs.update(frame_refs)
            stats = frame_result.get("stats", {})
            total_stats["total_refs"] += stats.get("total_refs", len(frame_refs))
            total_stats["interactive_refs"] += stats.get("interactive_refs", 0)
            total_stats["lines"] += stats.get("lines", 0) + 1
            total_stats["frames"] += 1
            remaining = max_refs - len(refs)

        snapshot_text = "\n".join(lines)
        total_stats["chars"] = len(snapshot_text)

        return {
            "ok": True,
            "format": "ai",
            "snapshot": snapshot_text,
            "refs": refs,
            "stats": total_stats,
        }
