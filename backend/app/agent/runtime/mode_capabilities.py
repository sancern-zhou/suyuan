"""Mode capability predicates for the ReAct runtime."""

from __future__ import annotations

from typing import Optional


NATIVE_MULTIMODAL_MODES = frozenset({"social", "chart"})


def supports_native_multimodal(mode: Optional[str]) -> bool:
    """Return whether a mode sends image attachments as native content blocks."""
    return (mode or "").strip().lower() in NATIVE_MULTIMODAL_MODES
