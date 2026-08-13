"""Compact Jiangsu air-quality API results for Agent-facing responses.

The provincial API carries many permanently empty instrument and audit fields
in every row.  Preserve the raw response as a session attachment, while giving
the Agent one current, deduplicated record per queried entity.
"""

from __future__ import annotations

from typing import Any


INLINE_RECORD_LIMIT = 24

_MISSING_VALUES = {"", "-", "—", "--", "null", "none", "nan", "-99", "-99.0", "-99.000"}
_USEFUL_FIELDS = {
    "name", "code", "cityName", "cityCode", "districtName", "districtCode",
    "positionName", "stationName", "stationCode", "uniqueCode", "timePoint",
    "dataType", "aqi", "qualityType", "primaryPollutant", "sO2", "nO2",
    "pM10", "co", "o3", "o3_8H", "pM2_5", "no", "nOx", "windSpeed",
    "windDirect", "pressure", "temperature", "humidity", "rainFall",
}


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in _MISSING_VALUES)


def _entity_key(record: dict[str, Any]) -> tuple[str, str]:
    for field in ("stationCode", "uniqueCode", "code", "cityCode", "districtCode"):
        if record.get(field) not in (None, ""):
            return field, str(record[field])
    for field in ("positionName", "stationName", "name", "cityName", "districtName"):
        if record.get(field):
            return field, str(record[field])
    return "record", repr(sorted(record.items()))


def compact_air_quality_records(records: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Remove placeholder fields, deduplicate rows, and keep latest entity state."""
    cleaned: list[dict[str, Any]] = []
    removed_empty_fields = 0
    for item in records:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for key, value in item.items():
            if key not in _USEFUL_FIELDS:
                continue
            if _is_missing(value):
                removed_empty_fields += 1
                continue
            row[key] = value.strip() if isinstance(value, str) else value
        if row:
            cleaned.append(row)

    unique_rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in cleaned:
        signature = tuple(sorted((key, str(value)) for key, value in row.items()))
        unique_rows.setdefault(signature, row)
    deduplicated = list(unique_rows.values())

    latest_by_entity: dict[tuple[str, str], dict[str, Any]] = {}
    for row in deduplicated:
        entity = _entity_key(row)
        current = latest_by_entity.get(entity)
        if current is None or str(row.get("timePoint") or "") >= str(current.get("timePoint") or ""):
            latest_by_entity[entity] = row
    latest = sorted(
        latest_by_entity.values(),
        key=lambda row: (str(row.get("name") or row.get("cityName") or row.get("positionName") or ""), str(row.get("code") or row.get("stationCode") or "")),
    )
    return latest, {
        "raw_record_count": len(records),
        "deduplicated_record_count": len(deduplicated),
        "latest_record_count": len(latest),
        "duplicate_record_count": len(cleaned) - len(deduplicated),
        "removed_empty_field_count": removed_empty_fields,
        "omitted_field_policy": "已剔除空值、-99、—、审计标记、主键和创建/修改时间等非分析字段；每个城市/区县/站点仅保留查询范围内最新记录。",
    }


def head_tail_sample(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a bounded but representative preview for Agent context."""
    head_size = INLINE_RECORD_LIMIT // 2
    return records[:head_size] + records[-(INLINE_RECORD_LIMIT - head_size):]


def externalize_compact_records(
    records: list[dict[str, Any]],
    *,
    context: Any,
    schema: str,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    """Persist oversized filtered results and return only a bounded preview.

    The saved document is a JSON array of the *filtered* records.  This makes
    it directly useful to a subsequent analysis tool, while callers can store
    a separate raw-response attachment for auditing if needed.
    """
    externalized = len(records) > INLINE_RECORD_LIMIT
    if not externalized:
        return records, None, {
            "data_complete": True,
            "record_count": len(records),
            "returned_records": len(records),
            "sample_strategy": "complete",
            "inline_record_limit": INLINE_RECORD_LIMIT,
            "externalized": False,
        }

    if context is None or not hasattr(context, "save_data"):
        # Preserve correctness for direct/unit invocations without a session.
        return records, None, {
            "data_complete": True,
            "record_count": len(records),
            "returned_records": len(records),
            "sample_strategy": "complete",
            "inline_record_limit": INLINE_RECORD_LIMIT,
            "externalized": False,
            "externalization_skipped": "execution context unavailable",
        }

    file_path = context.save_data(
        data=records,
        schema=schema,
        metadata={**metadata, "record_count": len(records), "root_type": "array", "filtered": True},
    )
    preview = head_tail_sample(records)
    return preview, file_path, {
        "data_complete": False,
        "record_count": len(records),
        "returned_records": len(preview),
        "sample_strategy": "head_tail",
        "inline_record_limit": INLINE_RECORD_LIMIT,
        "externalized": True,
        "data_structure": {
            "root_type": "array",
            "record_type": "object",
            "file_root_type": "array",
        },
    }
