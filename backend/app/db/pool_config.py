"""Environment-backed SQLAlchemy pool sizing for multi-process deployments."""

from __future__ import annotations

import os


def pool_int(name: str, default: int, *, minimum: int = 0) -> int:
    """Read a bounded non-negative pool setting without failing startup."""
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default
