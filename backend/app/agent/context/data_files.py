"""Session-scoped data file paths.

Data files are the runtime contract between tools. Paths exposed to the model
are canonical absolute filesystem paths so ordinary file tools and Python can
use them without translating a virtual namespace.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.utils.path_config import get_data_registry, resolve_agent_path


def get_data_root() -> Path:
    return get_data_registry()


def safe_file_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return stem or "data"


def session_data_dir(session_id: str) -> Path:
    path = get_data_root() / "sessions" / f"agent_session_{safe_file_stem(session_id)}" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def to_data_path(path: str | Path) -> str:
    """Return a validated canonical absolute path exposed to tools/LLMs."""
    resolved = resolve_agent_path(path)
    root = get_data_root()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Data file is outside the configured data root: {path}") from exc
    return str(resolved)


def resolve_data_path(
    file_path: str | Path,
    *,
    session_id: Optional[str] = None,
    must_exist: bool = True,
) -> Path:
    """Resolve and validate a model-visible data path."""
    raw = str(file_path or "").strip()
    if not raw:
        raise ValueError("file_path is required")

    root = get_data_root()
    resolved = resolve_agent_path(raw)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Data path escapes the configured data root: {raw}") from exc

    if session_id:
        session_prefix = Path("sessions") / f"agent_session_{safe_file_stem(session_id)}"
        if relative.parts[:1] == ("sessions",) and not relative.is_relative_to(session_prefix):
            raise PermissionError(f"Data path belongs to another session: {raw}")

    if must_exist and not resolved.is_file():
        raise FileNotFoundError(f"Data file does not exist: {raw}")
    return resolved


__all__ = [
    "get_data_root",
    "resolve_data_path",
    "safe_file_stem",
    "session_data_dir",
    "to_data_path",
]
