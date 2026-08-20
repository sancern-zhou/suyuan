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
# Reject-list approach: drop only known non-analytic columns instead of a
# allow-list, so new provincial metrics (IAQI breakdowns, visibility, ...)
# flow through automatically instead of being silently discarded.
_EXCLUDED_FIELDS = {"id", "createTime", "modifyTime", "calAreaType"}
_EXCLUDED_SUFFIXES = ("_Mark",)


def _is_excluded(key: str) -> bool:
    return key in _EXCLUDED_FIELDS or key.endswith(_EXCLUDED_SUFFIXES)


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
            if _is_excluded(key):
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
        "omitted_field_policy": "已剔除空值、-99、—、审计标记(_Mark)和主键、创建/修改时间、计算区域类型等非分析字段，并删除完全重复记录；其余字段（含分指标IAQI及新增指标）自动保留；保留查询范围内各城市/区县/站点的完整时间序列。",
    }


_STAT_SUFFIX_KINDS = [
    ("_SameCompare_Rank", "same_compare_rank"),
    ("_SameCompare_CityName", "same_compare_city_name"),
    ("_SameCompare_DistrictName", "same_compare_district_name"),
    ("_SameCompare_StationName", "same_compare_station_name"),
    ("_SameCompare", "same_compare"),
    ("_Rank", "rank"),
    ("_CityName", "city_name"),
    ("_DistrictName", "district_name"),
    ("_StationName", "station_name"),
]
_NAME_KINDS = {"city_name", "district_name", "station_name",
               "same_compare_city_name", "same_compare_district_name", "same_compare_station_name"}
_VALUE_KINDS = {"value", "rank", "same_compare", "same_compare_rank"}


def _stat_metric_and_kind(key: str) -> tuple[str, str] | None:
    """Split pM2_5_SameCompare_Rank style keys into (metric, kind)."""
    for suffix, kind in _STAT_SUFFIX_KINDS:
        if key.endswith(suffix):
            metric = key[: -len(suffix)]
            if metric:
                return metric, kind
    return None


def compact_statistics_records(records: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Re-shape rank-slot statistics rows so values keep their own holder.

    The source emits one row per rank slot: inside a row every metric family
    (pM2_5, o3_8h, ...) carries its own name/value/rank/same-compare columns
    that may point at different areas, and naming a row after the first name
    column would mis-attribute values to the wrong district or station.  The
    compact shape keeps one output row per source rank slot with
    ``metrics[metric] = {name fields..., value, rank, same_compare...}`` so
    each number stays attached to the area it names, while empty "—" padding
    is removed and rows without any metric values collapse into
    ``no_data_names``.
    """
    cleaned: list[dict[str, Any]] = []
    removed_empty_fields = 0
    no_data_names: list[str] = []
    seen_no_data: set[str] = set()

    def _track_no_data(name_value: Any) -> None:
        text = str(name_value)
        if text and text not in seen_no_data:
            seen_no_data.add(text)
            no_data_names.append(text)

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
            if pair is not None and pair[1] not in _NAME_KINDS:
                metric_names.add(pair[0])
        row: dict[str, Any] = {}
        metrics: dict[str, dict[str, Any]] = {}
        names_only: dict[str, dict[str, Any]] = {}
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
            if kind in _NAME_KINDS and metric not in metric_names:
                names_only.setdefault(metric, {}).setdefault(kind, value)
            else:
                metrics.setdefault(metric, {})[kind] = value
        # keep only metric families that carry at least one real value
        valued: dict[str, dict[str, Any]] = {}
        for metric, fields in metrics.items():
            if any(kind in _VALUE_KINDS for kind in fields):
                valued[metric] = fields
        has_payload = bool(valued) or any(key != "time_range" for key in row)
        if not has_payload:
            # the row only carries names: every metric lacks a value, so its
            # holders are areas without data for this statistic window
            for fields in names_only.values():
                holder = fields.get("district_name") or fields.get("station_name") or fields.get("city_name")
                if holder is not None:
                    _track_no_data(holder)
            continue
        if valued:
            row["metrics"] = dict(sorted(valued.items()))
        cleaned.append(row)

    return cleaned, {
        "raw_record_count": len(records),
        "compacted_record_count": len(cleaned),
        "removed_empty_field_count": removed_empty_fields,
        "no_data_names": no_data_names,
        "field_shape": (
            "每条记录对应一个名次档位：time_range + metrics{指标: {district_name/station_name, value, rank, "
            "same_compare, same_compare_rank, same_compare_*_name}}；同一档位内各指标的持有区域互相独立，"
            "数值不会跨区域错配；空值(—)字段已剔除，全部指标为空的区域仅列入 metadata.no_data_names。"
        ),
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
