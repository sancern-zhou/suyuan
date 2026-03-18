"""Snapshot Action Handler (SYNC version)

Handler for snapshot operation with support for LLM-optimized formats:
- ai: LLM-optimized format with role-based refs (default)
- aria: ARIA attribute-based format

Note: text format has been removed. Use format="ai" for better LLM support.
"""
import structlog

from ..config import config
from ..snapshot.generator import SnapshotGenerator
from ..refs.ref_resolver import set_global_refs

logger = structlog.get_logger()


def handle_snapshot(
    manager,
    session_id: str = "default",
    format: str = "ai",
    max_refs: int = 100,
    interactive_only: bool = False,
    compact: bool = True,  # Default to True for efficiency
    **kwargs
) -> dict:
    """Capture page snapshot with role-based refs

    Args:
        manager: BrowserManager instance
        session_id: Session identifier
        format: Snapshot format (ai/aria, default: ai)
        max_refs: Maximum number of refs (default: 100)
        interactive_only: Only include interactive elements (default: False)
        compact: Remove unnamed structural elements (default: True)

    Returns:
        {
            "ok": bool,
            "format": str,
            "snapshot": str,  # Formatted snapshot text
            "refs": dict,     # Reference context for resolver
            "stats": dict     # Statistics
        }
    """
    page = manager.get_active_page(session_id)

    # Validate format
    if format not in ["ai", "aria"]:
        raise ValueError(
            f"Unsupported snapshot format: {format}. "
            f"Supported formats: ai, aria. "
            f"text format has been removed; use format='ai' instead."
        )

    # Generate snapshot
    generator = SnapshotGenerator()
    result = generator.generate(
        page=page,
        format=format,
        max_refs=max_refs,
        interactive_only=interactive_only,
        compact=compact
    )

    # Store refs in global resolver for later use by act operations
    if "refs" in result:
        set_global_refs(result["refs"])

    logger.info(
        "browser_snapshot",
        session_id=session_id,
        format=format,
        compact=compact,
        refs=result.get("stats", {}).get("total_refs", 0),
        refs_stored=True
    )

    return result
