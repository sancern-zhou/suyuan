"""Shape Jiangsu air-quality API results for Agent-facing responses.

The provincial API carries many permanently empty instrument and audit fields
in every row. Preserve the complete time series while removing placeholder
fields and exact duplicate rows. Oversized results are externalized separately
so the inline Agent context can stay bounded without losing source records.
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


def compact_air_quality_records(records: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Remove placeholder fields and exact duplicates without collapsing time."""
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

    return deduplicated, {
        "raw_record_count": len(records),
        "deduplicated_record_count": len(deduplicated),
        "duplicate_record_count": len(cleaned) - len(deduplicated),
        "removed_empty_field_count": removed_empty_fields,
        "omitted_field_policy": "已剔除空值、-99、—、审计标记、主键和创建/修改时间等非分析字段，并删除完全重复记录；保留查询范围内各城市/区县/站点的完整时间序列。",
    }


_STAT_SUFFIX_KINDS = [
    ("_SameCompare_Rank", "same_compare_rank"),
    ("_SameCompare", "same_compare"),
    ("_Rank", "rank"),
    ("_CityName", "city_name"),
    ("_DistrictName", "district_name"),
    ("_StationName", "station_name"),
]


def _stat_metric_and_kind(key: str) -> tuple[str, str] | None:
    """Split pM2_5_SameCompare_Rank style keys into (metric, kind)."""
    for suffix, kind in _STAT_SUFFIX_KINDS:
        if key.endswith(suffix):
            metric = key[: -len(suffix)]
            if metric:
                return metric, kind
    return None


def compact_statistics_records(records: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse per-metric rank statistics rows into a compact nested shape.

    Source rows repeat the same city/district name for every metric and pad
    missing values with "—": a single row easily exceeds 3,000 characters.
    The compact shape keeps one name triple per row plus
    ``metrics[metric] = {value, rank, same_compare, same_compare_rank}``
    with missing entries removed.
    """
    cleaned: list[dict[str, Any]] = []
    removed_empty_fields = 0
    for item in records:
        if not isinstance(item, dict):
            continue
        present = {}
        for key, value in item.items():
            if _is_missing(value):
                removed_empty_fields += 1
                continue
            present[key] = value.strip() if isinstance(value, str) else value
        if not present:
            continue
        metric_names = set()
        for key in present:
            pair = _stat_metric_and_kind(key)
            if pair is not None and pair[1] not in {"city_name", "district_name", "station_name"}:
                metric_names.add(pair[0])
        row: dict[str, Any] = {}
        metrics: dict[str, dict[str, Any]] = {}
        for key, value in sorted(present.items()):
            if key == "dateTimeString":
                row["time_range"] = value
                continue
            pair = _stat_metric_and_kind(key)
            if pair is None:
                if key in metric_names:
                    metrics.setdefault(key, {})["value"] = value
                else:
                    row[key] = value
                continue
            metric, kind = pair
            if kind in {"city_name", "district_name", "station_name"}:
                row.setdefault(kind, value)
                continue
            metrics.setdefault(metric, {})[kind] = value
        if metrics:
            row["metrics"] = metrics
        cleaned.append(row)

    return cleaned, {
        "raw_record_count": len(records),
        "compacted_record_count": len(cleaned),
        "removed_empty_field_count": removed_empty_fields,
        "field_shape": "每条记录含 time_range、city_name/district_name/station_name 与 metrics{指标: {value, rank, same_compare, same_compare_rank}}；空值(—)字段已剔除。",
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
