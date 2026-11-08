"""Validate files declared by a child agent at the submission boundary."""

from collections.abc import Mapping
from typing import Any

from app.utils.path_config import resolve_agent_path


def _json_type(value: Any) -> str:
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def validate_deliverable_entries(entries: Any) -> list[dict[str, str]]:
    """Require declared deliverable paths to identify real files.

    Format and business completeness belong to the caller's optional result
    schema and the parent agent's review, not to the DAG transport layer.
    """
    if entries is None:
        return []
    if not isinstance(entries, list):
        return [{"path": "$.deliverables", "expected": "array of {path}", "got": _json_type(entries)}]
    violations: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        prefix = f"$.deliverables[{index}]"
        if not isinstance(entry, Mapping):
            violations.append({"path": prefix, "expected": "object with path", "got": _json_type(entry)})
            continue
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            violations.append({"path": f"{prefix}.path", "expected": "nonempty file path", "got": "missing"})
            continue
        try:
            path = resolve_agent_path(raw_path)
        except (OSError, ValueError, TypeError) as exc:
            violations.append({"path": f"{prefix}.path", "expected": "resolvable file path", "got": str(exc)})
            continue
        if not path.is_file():
            violations.append({"path": f"{prefix}.path", "expected": "existing file", "got": "not found"})
    return violations
