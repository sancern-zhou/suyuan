"""Bound structured data before it enters the model context."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List


INLINE_RECORD_LIMIT = 24
FIELD_SCHEMA_SCAN_LIMIT = 200
_RECORD_LIST_KEYS = ("data", "rows", "records", "resultData")
_PATH_KEYS = {
    "file_path",
    "file_paths",
    "report_file_path",
    "report_file_paths",
    "source_file_path",
    "source_file_paths",
}
_COUNT_KEYS = ("record_count", "total_count", "total_records", "original_count")


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def build_field_schema(records: Iterable[Any]) -> List[Dict[str, Any]]:
    """Describe the union of top-level fields without copying record values."""
    rows = records if isinstance(records, list) else list(records)
    field_order: List[str] = []
    stats: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        for field, value in row.items():
            name = str(field)
            if name not in stats:
                field_order.append(name)
                stats[name] = {"present_count": 0, "null_count": 0, "types": Counter()}
            info = stats[name]
            info["present_count"] += 1
            value_type = _value_type(value)
            info["types"][value_type] += 1
            if value is None:
                info["null_count"] += 1

    schema: List[Dict[str, Any]] = []
    for name in field_order:
        info = stats[name]
        schema.append({
            "name": name,
            "types": list(info["types"].keys()),
            "present_count": info["present_count"],
            "null_count": info["null_count"],
        })
    return schema


def _head_tail_sample(records: List[Any]) -> List[Any]:
    head_count = INLINE_RECORD_LIMIT // 2
    tail_count = INLINE_RECORD_LIMIT - head_count
    return records[:head_count] + records[-tail_count:]


def _schema_sample(records: List[Any]) -> List[Any]:
    if len(records) <= FIELD_SCHEMA_SCAN_LIMIT:
        return records
    head_count = FIELD_SCHEMA_SCAN_LIMIT // 2
    tail_count = FIELD_SCHEMA_SCAN_LIMIT - head_count
    return records[:head_count] + records[-tail_count:]


def _has_file_path(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PATH_KEYS and item:
                return True
            if key in _RECORD_LIST_KEYS:
                continue
            if _has_file_path(item):
                return True
    elif isinstance(value, list):
        return any(_has_file_path(item) for item in value)
    return False


def _declared_record_count(result: Dict[str, Any], observed: int) -> int:
    candidates: List[int] = []
    for container in (result, result.get("metadata")):
        if not isinstance(container, dict):
            continue
        for key in _COUNT_KEYS:
            value = container.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= observed:
                candidates.append(value)
    return max(candidates, default=observed)


def shape_data_result_for_context(result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the 24-record inline contract to a standardized tool result.

    Large lists are sampled only when the complete result has a file path. This
    prevents accidental data loss for tools that have not yet adopted the path
    contract.
    """
    if not isinstance(result, dict) or result.get("success") is False:
        return result

    containers: List[tuple[Dict[str, Any], str, List[Any]]] = []
    for key in _RECORD_LIST_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            containers.append((result, key, value))

    data = result.get("data")
    if isinstance(data, dict):
        for key in _RECORD_LIST_KEYS[1:]:
            value = data.get(key)
            if isinstance(value, list):
                containers.append((data, key, value))

    if not containers:
        return result

    shaped = dict(result)
    shaped_metadata = dict(result.get("metadata") or {})
    shaped["metadata"] = shaped_metadata
    if isinstance(data, dict):
        shaped_data = dict(data)
        shaped["data"] = shaped_data
        containers = [
            (shaped_data if container is data else shaped, key, records)
            for container, key, records in containers
        ]
    else:
        containers = [(shaped, key, records) for _, key, records in containers]

    has_path = _has_file_path(shaped)
    descriptions: List[Dict[str, Any]] = []
    for container, key, records in containers:
        observed = len(records)
        total = _declared_record_count(shaped, observed)
        complete = total <= INLINE_RECORD_LIMIT
        returned = observed
        strategy = "complete"
        if not complete and has_path and observed > INLINE_RECORD_LIMIT:
            container[key] = _head_tail_sample(records)
            returned = INLINE_RECORD_LIMIT
            strategy = "head_tail"
        elif not complete and has_path:
            strategy = "provided_sample"
        elif not complete:
            # Do not silently discard records when no durable full-data path exists.
            if observed == total:
                complete = True
                strategy = "complete_no_file_path"
            else:
                strategy = "provided_sample_no_file_path"

        schema_records = _schema_sample(records)
        descriptions.append({
            "field": key,
            "data_complete": complete,
            "record_count": total,
            "returned_records": returned,
            "sample_strategy": strategy,
            "field_schema": build_field_schema(schema_records),
            "field_schema_scanned_records": len(schema_records),
        })

    primary = descriptions[0]
    shaped["data_complete"] = primary["data_complete"]
    shaped["record_count"] = primary["record_count"]
    shaped["returned_records"] = primary["returned_records"]
    shaped["sample_strategy"] = primary["sample_strategy"]
    shaped["field_schema"] = primary["field_schema"]
    shaped_metadata["context_data"] = {
        "inline_record_limit": INLINE_RECORD_LIMIT,
        "datasets": descriptions,
    }
    return shaped


def persist_large_inline_data(
    result: Dict[str, Any],
    *,
    context: Any,
    tool_name: str,
) -> Dict[str, Any]:
    """Persist an unexternalized large top-level data list when context permits."""
    if not isinstance(result, dict) or _has_file_path(result):
        return result
    records = result.get("data")
    if not isinstance(records, list) or len(records) <= INLINE_RECORD_LIMIT:
        return result
    if context is None or not hasattr(context, "save_data"):
        return result

    file_path = context.save_data(
        records,
        schema=f"{tool_name}_result",
        metadata={"source_tool": tool_name, "record_count": len(records)},
    )
    persisted = dict(result)
    persisted["file_path"] = file_path
    metadata = dict(result.get("metadata") or {})
    metadata.setdefault("file_path", file_path)
    persisted["metadata"] = metadata
    return persisted


__all__ = [
    "FIELD_SCHEMA_SCAN_LIMIT",
    "INLINE_RECORD_LIMIT",
    "build_field_schema",
    "persist_large_inline_data",
    "shape_data_result_for_context",
]
