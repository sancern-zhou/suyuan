"""Mode capability predicates for the ReAct runtime."""

from __future__ import annotations

from typing import Optional


def supports_native_multimodal(mode: Optional[str]) -> bool:
    """Return whether the Agent runtime sends images as native content blocks.

    Native multimodal support is a global Agent capability. The argument is
    retained so callers keep a stable capability-checking API, while unknown
    and future modes inherit the capability automatically.
    """
    return True
