"""Canonical, bounded paths for mode memory storage."""

from __future__ import annotations

from pathlib import Path

from app.utils.path_config import get_memory_dir, get_social_memory_dir, resolve_agent_path

_MAX_SEGMENT_LENGTH = 128
_FORBIDDEN_SEGMENTS = {".", ".."}
_FORBIDDEN_CHARS = ("/", "\\", "\x00")


def safe_memory_segment(value: str, *, field: str) -> str:
    """Validate one path segment, allowing CJK/`@`/`.` user IDs (prod data)."""
    raw = str(value or "").strip()
    if not raw or len(raw) > _MAX_SEGMENT_LENGTH:
        raise ValueError(f"invalid memory {field}")
    if raw in _FORBIDDEN_SEGMENTS or any(ch in raw for ch in _FORBIDDEN_CHARS):
        raise ValueError(f"invalid memory {field}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise ValueError(f"invalid memory {field}")
    return raw


def memory_workspace(mode: str, user_id: str | None = None, workspace: Path | None = None) -> Path:
    """Resolve the canonical workspace for one mode."""
    safe_mode = safe_memory_segment(mode, field="mode")
    if safe_mode == "memory_consolidator":
        raise ValueError("memory_consolidator is not a business memory mode")
    if safe_mode == "social":
        if not user_id or user_id == "global":
            raise ValueError("social memory requires a user ID")
        base = resolve_agent_path(workspace) if workspace is not None else get_social_memory_dir()
        path = base / safe_memory_segment(user_id.replace(":", "_"), field="user ID")
    else:
        base = resolve_agent_path(workspace) if workspace is not None else get_memory_dir()
        path = base / safe_mode
    root = base.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("memory path escapes configured root") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
