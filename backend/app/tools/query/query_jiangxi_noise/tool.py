"""Split Jiangxi noise query tools for Agent use."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import structlog

from app.agent.context.execution_context import ExecutionContext
from app.external_apis.jiangxi_noise_api_client import (
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
    normalize_to_shanghai,
)
from app.services.data_registry import data_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.station_directory import (
    JIANGXI_CITY_CODES,
    JiangxiNoiseStation,
    resolve_city_names,
    resolve_station_records,
)
from app.tools.resource_declarations import data_file_resource
from app.tools.resource_refs import build_data_file_ref

logger = structlog.get_logger()

MAX_QUERY_RANGE = timedelta(days=31)
DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 1000
DEFAULT_MAX_PAGES = 20
MAX_MAX_PAGES = 100
PREVIEW_LIMIT = 24
DEFAULT_ORIGINAL_DATA_TYPE = 0
DEFAULT_AUDITED_DATA_TYPE = 1
DATA_TYPE_LABELS = {
    DEFAULT_ORIGINAL_DATA_TYPE: "原始数据",
    DEFAULT_AUDITED_DATA_TYPE: "审核数据",
}
FUNCTIONAL_AREA_DEFINITIONS: dict[str, dict[str, Any]] = {
    "1": {"functional_area_type": "1", "functional_area_name": "1类功能区"},
    "2": {"functional_area_type": "2", "functional_area_name": "2类功能区"},
    "3": {"functional_area_type": "3", "functional_area_name": "3类功能区"},
    "4": {"functional_area_type": "4", "functional_area_name": "4类功能区"},
}
CITY_FUNCTIONAL_AREA_COLUMNS = {
    "leq_1": "1类功能区",
    "leq_2": "2类功能区",
    "leq_3": "3类功能区",
    "leq_4": "4类功能区",
}
STATION_TYPE_FUNCTIONAL_AREA = {
    "4": "1",
    "5": "2",
    "6": "3",
    "7": "4",
}
UNIQUE_CODE_FUNCTIONAL_AREA_PREFIX = {
    "31": "1",
    "32": "2",
    "33": "3",
    "34": "4",
}


class ToolInputError(ValueError):
    """Tool input error that is safe to return to the Agent."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_time(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError("invalid_time", f"{field_name} 不能为空")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ToolInputError(
            "invalid_time",
            f"{field_name} 必须使用 ISO 8601 格式，例如 2026-07-30T00:00:00+08:00",
        ) from exc
    return normalize_to_shanghai(parsed)


def _parse_time_range(
    start_time: str,
    end_time: str,
    *,
    max_range: timedelta | None = MAX_QUERY_RANGE,
) -> tuple[datetime, datetime]:
    start = _parse_time(start_time, "start_time")
    end = _parse_time(end_time, "end_time")
    if start > end:
        raise ToolInputError("invalid_time_range", "start_time 不能晚于 end_time")
    if max_range is not None and end - start > max_range:
        raise ToolInputError(
            "time_range_too_large",
            f"单次查询时间范围不能超过 {max_range.days} 天",
        )
    return start, end


def _clean_string_list(values: Any, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ToolInputError("invalid_argument", f"{field_name} 必须是字符串数组")
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ToolInputError("invalid_argument", f"{field_name} 只能包含非空字符串")
        item = value.strip()
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def _validate_data_type(data_type: Any) -> int:
    if isinstance(data_type, bool):
        raise ToolInputError("invalid_data_type", "data_type 必须是 0 或 1；0=原始数据，1=审核数据")
    if isinstance(data_type, int):
        value = data_type
    elif isinstance(data_type, str) and data_type.strip() in {"0", "1"}:
        value = int(data_type.strip())
    else:
        raise ToolInputError("invalid_data_type", "data_type 必须是 0 或 1；0=原始数据，1=审核数据")
    if value not in DATA_TYPE_LABELS:
        raise ToolInputError("invalid_data_type", "data_type 必须是 0 或 1；0=原始数据，1=审核数据")
    return value


def _data_type_description(default_value: int) -> str:
    default_label = DATA_TYPE_LABELS[default_value]
    return (
        "可选参数，对应江西噪声平台接口 dataType。可选值：1=审核数据，0=原始数据；"
        f"默认查询 {default_value}（{default_label}）。"
    )


def _data_type_schema(default_value: int) -> dict[str, Any]:
    return {
        "type": "integer",
        "enum": [DEFAULT_AUDITED_DATA_TYPE, DEFAULT_ORIGINAL_DATA_TYPE],
        "default": default_value,
        "description": _data_type_description(default_value),
    }


def _resolve_data_type_argument(
    data_type: Any,
    extra_kwargs: dict[str, Any],
    default_value: int,
) -> int:
    if "review_status" in extra_kwargs:
        raise ToolInputError(
            "invalid_argument",
            "review_status 不表示原始/审核数据；请使用 data_type，1=审核数据，0=原始数据",
        )

    if "dataType" in extra_kwargs:
        alias_value = _validate_data_type(extra_kwargs["dataType"])
        if data_type is not None and _validate_data_type(data_type) != alias_value:
            raise ToolInputError("invalid_data_type", "data_type 与 dataType 不能同时传不同值")
        return alias_value

    if data_type is None:
        data_type = default_value
    return _validate_data_type(data_type)


def _validate_page_size(page_size: Any) -> int:
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise ToolInputError("invalid_page_size", f"page_size 必须是 1 至 {MAX_PAGE_SIZE} 的整数")
    return page_size


def _validate_max_pages(max_pages: Any) -> int:
    if (
        isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or not 1 <= max_pages <= MAX_MAX_PAGES
    ):
        raise ToolInputError("invalid_max_pages", f"max_pages 必须是 1 至 {MAX_MAX_PAGES} 的整数")
    return max_pages


def _station_metadata(stations: list[JiangxiNoiseStation]) -> dict[str, dict[str, Any]]:
    return {station.station_code: station.as_dict() for station in stations}


NOISE_RECORD_KEEP_FIELDS = frozenset(
    {
        # 工具规范化字段
        "time",
        "station_code",
        "city_code",
        "city_name",
        "province_name",
        "area_name",
        # 任意时段达标率统计
        "build_station_count",
        "monitor_day_count",
        "monitor_night_count",
        "day_compliance_count",
        "night_compliance_count",
        "day_compliance_rate",
        "night_compliance_rate",
        "day_compliance_rate_0",
        "night_compliance_rate_0",
        "day_compliance_rate_1",
        "night_compliance_rate_1",
        "day_compliance_rate_2",
        "night_compliance_rate_2",
        "day_compliance_rate_3",
        "night_compliance_rate_3",
        "day_compliance_rate_4a",
        "night_compliance_rate_4a",
        "day_compliance_rate_4b",
        "night_compliance_rate_4b",
        "ld_compliance_rate",
        "ln_compliance_rate",
        "is_ld_compliant",
        "is_ln_compliant",
        # 城市小时功能区 Leq
        "leq_1",
        "leq_2",
        "leq_3",
        "leq_4",
        # 噪声核心指标
        "leq",
        "ldn",
        "ld",
        "ld_Decimal",
        "ln",
        "ln_Decimal",
        "lnMax",
        "l5",
        "l10",
        "l50",
        "l90",
        "l95",
        "lMin",
        "lMax",
        "sd",
        "la",
        "vdr",
        "vdRd",
        "vdRn",
        # 超标标志
        "isOverStandard",
        "isLdOverStandard",
        "isLnOverStandard",
        # 气象
        "windSpeed",
        "windDirect",
        "windDirectName",
        "pressure",
        "temperature",
        "humidity",
        "rainfall",
        # 车流量与交通
        "smallCarFlow",
        "mediumCarFlow",
        "largeCarFlow",
        "largestCarFlow",
        "totalCarFlow",
        "share",
        "avgSpeed",
    }
)

NOISE_FIELD_ALIASES = {
    "stationCode": "station_code",
    "StationCode": "station_code",
    "code": "station_code",
    "Code": "station_code",
    "stationName": "station_name",
    "StationName": "station_name",
    "name": "station_name",
    "Name": "station_name",
    "cityCode": "city_code",
    "CityCode": "city_code",
    "cityName": "city_name",
    "CityName": "city_name",
    "provinceName": "province_name",
    "ProvinceName": "province_name",
    "proName": "province_name",
    "ProName": "province_name",
    "areaName": "area_name",
    "AreaName": "area_name",
    "districtCode": "district_code",
    "DistrictCode": "district_code",
    "districtName": "district_name",
    "DistrictName": "district_name",
    "stationType": "station_type_id",
    "StationType": "station_type_id",
    "stationTypeId": "station_type_id",
    "StationTypeId": "station_type_id",
    "typeId": "station_type_id",
    "TypeId": "station_type_id",
    "uniqueCode": "unique_code",
    "UniqueCode": "unique_code",
    "timePoint": "time",
    "TimePoint": "time",
    "timePointStr": "time",
    "TimePointStr": "time",
    "dateTimeStr": "time",
    "DateTimeStr": "time",
    "buildStationCount": "build_station_count",
    "monitorStationDayCount": "monitor_day_count",
    "monitorStationNightCount": "monitor_night_count",
    "dayTimeComplianceCount": "day_compliance_count",
    "nightTimeComplianceCount": "night_compliance_count",
    "dayTimeComplianceRate": "day_compliance_rate",
    "nightTimeComplianceRate": "night_compliance_rate",
    "dayTime_30_Rate": "day_compliance_rate_0",
    "nightTime_30_Rate": "night_compliance_rate_0",
    "dayTime_31_Rate": "day_compliance_rate_1",
    "nightTime_31_Rate": "night_compliance_rate_1",
    "dayTime_32_Rate": "day_compliance_rate_2",
    "nightTime_32_Rate": "night_compliance_rate_2",
    "dayTime_33_Rate": "day_compliance_rate_3",
    "nightTime_33_Rate": "night_compliance_rate_3",
    "dayTime_34_Rate": "day_compliance_rate_4a",
    "nightTime_34_Rate": "night_compliance_rate_4a",
    "dayTime_35_Rate": "day_compliance_rate_4b",
    "nightTime_35_Rate": "night_compliance_rate_4b",
    "ld_Value": "ld",
    "ln_Value": "ln",
    "ldn_Value": "ldn",
    "vdr_Value": "vdr",
    "ldStandardReachingRate": "ld_compliance_rate",
    "lnStandardReachingRate": "ln_compliance_rate",
    "isLdStandardReaching": "is_ld_compliant",
    "isLnStandardReaching": "is_ln_compliant",
}

NOISE_FIELD_ALIAS_PRIORITY = {
    "time": 30,
    "timePointStr": 20,
    "TimePointStr": 20,
    "timePoint": 10,
    "TimePoint": 10,
}

NOISE_RECORD_FIELD_ORDER = (
    "time",
    "station_code",
    "city_name",
    "city_code",
    "province_name",
    "area_name",
    "build_station_count",
    "monitor_day_count",
    "monitor_night_count",
    "day_compliance_count",
    "night_compliance_count",
    "day_compliance_rate",
    "night_compliance_rate",
    "ld_compliance_rate",
    "ln_compliance_rate",
    "is_ld_compliant",
    "is_ln_compliant",
    "day_compliance_rate_0",
    "night_compliance_rate_0",
    "day_compliance_rate_1",
    "night_compliance_rate_1",
    "day_compliance_rate_2",
    "night_compliance_rate_2",
    "day_compliance_rate_3",
    "night_compliance_rate_3",
    "day_compliance_rate_4a",
    "night_compliance_rate_4a",
    "day_compliance_rate_4b",
    "night_compliance_rate_4b",
    "leq",
    "ldn",
    "ld",
    "ln",
    "lnMax",
    "leq_1",
    "leq_2",
    "leq_3",
    "leq_4",
    "l5",
    "l10",
    "l50",
    "l90",
    "l95",
    "lMin",
    "lMax",
    "sd",
    "la",
    "vdr",
    "vdRd",
    "vdRn",
    "isOverStandard",
    "isLdOverStandard",
    "isLnOverStandard",
    "windSpeed",
    "windDirect",
    "windDirectName",
    "pressure",
    "temperature",
    "humidity",
    "rainfall",
    "smallCarFlow",
    "mediumCarFlow",
    "largeCarFlow",
    "largestCarFlow",
    "totalCarFlow",
    "share",
    "avgSpeed",
)

NOISE_ZERO_AS_MISSING_FIELDS = frozenset(
    {
        "leq",
        "ldn",
        "ld",
        "ld_Decimal",
        "ln",
        "ln_Decimal",
        "lnMax",
        "la",
        "l5",
        "l10",
        "l50",
        "l90",
        "l95",
        "lMin",
        "lMax",
        "leq_1",
        "leq_2",
        "leq_3",
        "leq_4",
    }
)

NOISE_PLACEHOLDER_VALUES = frozenset({-99, -99.0})

NOISE_EMPTY_TEXT_VALUES = frozenset(
    {
        "",
        "-",
        "--",
        "—",
        "null",
        "none",
        "n/a",
        "nan",
        "无",
    }
)


def _noise_value_drop_reason(field: str, value: Any) -> str | None:
    """识别空值、占位值和只在部分指标中表示无数据的零值。

    布尔值（False）属于有效标志，不参与零值剔除。
    """
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if value in NOISE_PLACEHOLDER_VALUES:
            return "placeholder"
        if value == 0 and field in NOISE_ZERO_AS_MISSING_FIELDS:
            return "zero"
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in NOISE_EMPTY_TEXT_VALUES:
            return "empty"
        try:
            number = float(stripped)
        except ValueError:
            return None
        if number in NOISE_PLACEHOLDER_VALUES:
            return "placeholder"
        if number == 0 and field in NOISE_ZERO_AS_MISSING_FIELDS:
            return "zero"
        return None
    return None


def _normalize_noise_record_fields(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    priorities: dict[str, int] = {}
    for field, value in record.items():
        target = NOISE_FIELD_ALIASES.get(field, field)
        priority = NOISE_FIELD_ALIAS_PRIORITY.get(field, 0)
        if target in normalized:
            old_value_is_valid = _noise_value_drop_reason(target, normalized[target]) is None
            new_value_is_valid = _noise_value_drop_reason(target, value) is None
            if old_value_is_valid and (
                not new_value_is_valid or priority <= priorities.get(target, 0)
            ):
                continue
        normalized[target] = value
        priorities[target] = priority
    return normalized


def _ordered_noise_record(record: dict[str, Any]) -> dict[str, Any]:
    ordered = {field: record[field] for field in NOISE_RECORD_FIELD_ORDER if field in record}
    for field, value in record.items():
        if field not in ordered:
            ordered[field] = value
    return ordered


def _filter_noise_record_fields(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """按白名单裁剪噪声记录字段，移除冗余字段以缩短上下文。

    白名单之外或重复表达的字段直接移除；白名单内字段会剔除空值和 -99/—
    等占位值。零值只在声级类指标中视为无数据，气象、车流量和超标标志
    的 0 均保留。
    返回 (过滤后记录, 剔除统计)，其中 zero_value 统计零值被剔除的字段
    及受影响记录数。
    """
    filtered: list[dict[str, Any]] = []
    zero_dropped_fields: dict[str, int] = {}
    zero_dropped_records: set[int] = set()
    for record_index, record in enumerate(records):
        item: dict[str, Any] = {}
        normalized = _normalize_noise_record_fields(record)
        for field, value in normalized.items():
            if field not in NOISE_RECORD_KEEP_FIELDS:
                continue
            reason = _noise_value_drop_reason(field, value)
            if reason is None:
                item[field] = value
            elif reason == "zero":
                zero_dropped_fields[field] = zero_dropped_fields.get(field, 0) + 1
                zero_dropped_records.add(record_index)
        filtered.append(_ordered_noise_record(item))
    drop_stats: dict[str, Any] = {
        "zero_value": {
            "dropped_fields": dict(sorted(zero_dropped_fields.items())),
            "records_affected": len(zero_dropped_records),
        }
    }
    return filtered, drop_stats


def _functional_area_definition(area_type: str) -> dict[str, Any]:
    return dict(FUNCTIONAL_AREA_DEFINITIONS[area_type])


def _first_non_empty_field(
    record: dict[str, Any],
    field_names: tuple[str, ...],
) -> tuple[Any, str | None]:
    for field_name in field_names:
        value = record.get(field_name)
        if value is not None and str(value).strip():
            return value, field_name
    return None, None


def _station_functional_area_from_values(
    *,
    station_type_id: Any,
    unique_code: Any,
    station_type_source: str,
    unique_code_source: str,
) -> dict[str, Any] | None:
    station_type_id = str(station_type_id or "").strip()
    area_type = STATION_TYPE_FUNCTIONAL_AREA.get(station_type_id)
    source = station_type_source
    if not area_type:
        unique_code = str(unique_code or "").strip()
        prefix = unique_code[6:8] if len(unique_code) >= 8 else ""
        area_type = UNIQUE_CODE_FUNCTIONAL_AREA_PREFIX.get(prefix)
        source = unique_code_source
    if not area_type:
        return None
    definition = _functional_area_definition(area_type)
    definition["source"] = source
    return definition


def _station_functional_area(station: JiangxiNoiseStation) -> dict[str, Any] | None:
    return _station_functional_area_from_values(
        station_type_id=station.station_type_id,
        unique_code=station.unique_code,
        station_type_source="station_directory.station_type_id",
        unique_code_source="station_directory.unique_code",
    )


def _station_functional_area_mapping_metadata() -> dict[str, dict[str, Any]]:
    return {
        station_type_id: _functional_area_definition(area_type)
        for station_type_id, area_type in STATION_TYPE_FUNCTIONAL_AREA.items()
    }


def _attach_station_directory_fields(
    records: list[dict[str, Any]],
    stations: list[JiangxiNoiseStation],
) -> list[dict[str, Any]]:
    by_code = _station_metadata(stations)
    enriched: list[dict[str, Any]] = []
    for record in records:
        item = _normalize_noise_record_fields(record)
        raw_code = (
            item.get("station_code")
            or item.get("stationCode")
            or item.get("StationCode")
            or item.get("code")
            or item.get("Code")
        )
        station = by_code.get(str(raw_code or "").strip().upper())
        api_station_type_id, api_station_type_field = _first_non_empty_field(
            item,
            ("station_type_id", "stationTypeId", "StationTypeId", "typeId", "TypeId"),
        )
        api_unique_code, api_unique_code_field = _first_non_empty_field(
            item,
            ("unique_code", "uniqueCode", "UniqueCode"),
        )
        station_type_id = api_station_type_id
        station_type_source = api_station_type_field or "station_directory.station_type_id"
        unique_code = api_unique_code
        unique_code_source = api_unique_code_field or "station_directory.unique_code"
        if station:
            item.setdefault("station_code", station["station_code"])
            item.setdefault("station_name", station["name"])
            item.setdefault("city_name", station["city_name"])
            item.setdefault("city_code", station["city_code"])
            item.setdefault("district_code", station["district_code"])
            item.setdefault("longitude", station["longitude"])
            item.setdefault("latitude", station["latitude"])
            item.setdefault("address", station["address"])
            if station_type_id is None:
                station_type_id = station["station_type_id"]
                station_type_source = "station_directory.station_type_id"
            if unique_code is None:
                unique_code = station["unique_code"]
                unique_code_source = "station_directory.unique_code"
        if station_type_id is not None and str(station_type_id).strip():
            item.setdefault("station_type_id", str(station_type_id).strip())
        if unique_code is not None and str(unique_code).strip():
            item.setdefault("unique_code", str(unique_code).strip())
        functional_area = _station_functional_area_from_values(
            station_type_id=station_type_id,
            unique_code=unique_code,
            station_type_source=station_type_source,
            unique_code_source=unique_code_source,
        )
        if functional_area:
            item.setdefault("functional_area", functional_area)
        enriched.append(item)
    return enriched


STATION_STATIC_FIELDS = (
    "station_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "longitude",
    "latitude",
    "station_type_id",
    "unique_code",
    "functional_area",
)

STATION_METADATA_FIELDS = (
    "station_name",
    "city_name",
    "district_name",
    "longitude",
    "latitude",
    "functional_area",
)


def _compact_functional_area(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    area_type = value.get("functional_area_type")
    area_name = value.get("functional_area_name")
    if area_type and area_name:
        return {"type": str(area_type), "name": area_name}
    return value


def _station_static_metadata(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """从已附加站点目录字段的记录中提取每站一份的静态信息。"""
    stations_meta: dict[str, dict[str, Any]] = {}
    for record in records:
        code = record.get("station_code")
        if not code or code in stations_meta:
            continue
        meta: dict[str, Any] = {}
        for field in STATION_METADATA_FIELDS:
            value = record.get(field)
            if _noise_value_drop_reason(field, value) is not None:
                continue
            meta[field] = _compact_functional_area(value) if field == "functional_area" else value
        stations_meta[code] = meta
    return stations_meta


def _strip_station_static_fields(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从每条记录中移除静态站点字段，避免跨记录重复占用上下文。"""
    stripped: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        for field in (*STATION_STATIC_FIELDS, "name", "cityName", "cityCode", "districtName"):
            item.pop(field, None)
        stripped.append(item)
    return stripped


async def _fetch_all_pages(
    query: Callable[..., Awaitable[dict[str, Any]]],
    *,
    page_size: int,
    max_pages: int,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], int, int, bool]:
    records: list[dict[str, Any]] = []
    total_count = 0
    skip_count = 0
    pages_fetched = 0

    while pages_fetched < max_pages:
        result = await query(
            **kwargs,
            max_result_count=page_size,
            skip_count=skip_count,
        )
        page_records = result.get("data") or []
        if not isinstance(page_records, list):
            raise JiangxiNoiseClientError("invalid_response", "江西噪声平台数据列表格式不正确")

        if pages_fetched == 0:
            raw_total = result.get("total_count", len(page_records))
            total_count = raw_total if isinstance(raw_total, int) else len(page_records)

        records.extend(item for item in page_records if isinstance(item, dict))
        pages_fetched += 1
        skip_count += len(page_records)

        if not page_records or len(records) >= total_count or len(page_records) < page_size:
            break

    truncated = total_count > len(records)
    return records, total_count, pages_fetched, truncated


def _save_records(
    *,
    context: ExecutionContext | None,
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str | None:
    if not records:
        return None
    try:
        if context is not None:
            return str(
                context.save_data(
                    data=records,
                    schema="jiangxi_noise",
                    metadata=metadata,
                )
            )
        entry = data_registry.register_dataset(
            schema="jiangxi_noise",
            version="v1",
            records=records,
            metadata=metadata,
            sample_size=PREVIEW_LIMIT,
        )
        return str(entry.dataset_path.resolve())
    except Exception as exc:
        logger.warning(
            "jiangxi_noise_data_externalize_failed",
            error=str(exc),
            tool_name=metadata.get("tool_name"),
        )
        return None


def _success_response(
    *,
    tool_name: str,
    records: list[dict[str, Any]],
    total_count: int,
    pages_fetched: int,
    pagination_truncated: bool,
    metadata: dict[str, Any],
    summary_prefix: str,
    context: ExecutionContext | None,
) -> dict[str, Any]:
    records, drop_stats = _filter_noise_record_fields(records)
    field_filtering: dict[str, Any] = {
        "applied": True,
        "note": "已统一字段名；移除 *_Mark、id/dataType、审计时间戳、空值、-99/—占位值和重复静态站点字段；气象/车流/超标标志的 0 保留。",
    }
    if drop_stats["zero_value"]["dropped_fields"]:
        field_filtering["zero_value_removal"] = drop_stats["zero_value"]
    full_metadata = {
        "schema_version": "v2.0",
        "tool_name": tool_name,
        "total_records": len(records),
        "api_total_count": total_count,
        "pages_fetched": pages_fetched,
        "pagination_truncated": pagination_truncated,
        "field_filtering": field_filtering,
        **metadata,
    }
    should_externalize = len(records) > PREVIEW_LIMIT or pagination_truncated
    file_path = (
        _save_records(context=context, records=records, metadata=full_metadata)
        if should_externalize
        else None
    )
    preview = records[:PREVIEW_LIMIT] if file_path else records
    full_metadata["data_records"] = len(preview)
    full_metadata["data_is_complete_for_requested_scope"] = not file_path and not pagination_truncated
    if file_path:
        full_metadata["file_path"] = file_path
        full_metadata["result_externalized"] = True
        full_metadata["file_usage"] = {
            "python": f"records = load_data({file_path!r})",
            "note": "data 返回预览记录；完整噪声数据已保存到 file_path。",
        }

    summary = f"{summary_prefix}，返回 {len(records)} 条记录"
    if file_path:
        summary += f"；完整数据已保存为 file_path: {file_path}，data 返回前 {len(preview)} 条预览"
    if pagination_truncated:
        summary += "；结果受 max_pages 限制未拉取完整，请增大 max_pages 或缩小查询范围"

    result: dict[str, Any] = {
        "status": "success" if records else "empty",
        "success": True,
        "data": preview,
        "metadata": full_metadata,
        "summary": summary,
    }
    if file_path:
        result["file_path"] = file_path
        result["refs"] = {"data": [build_data_file_ref(file_path, usage="generated")]}
        result["resources"] = [
            data_file_resource(
                file_path,
                tool_name=tool_name,
                label=f"{summary_prefix}完整数据",
                metadata={
                    "summary": summary,
                    "record_count": len(records),
                    "schema": "jiangxi_noise",
                },
            )
        ]
    return result


def _error_response(
    *,
    tool_name: str,
    code: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "data": [],
        "metadata": {
            "schema_version": "v2.0",
            "tool_name": tool_name,
            "error_code": code,
            **(metadata or {}),
        },
        "summary": message,
        "error": message,
        "error_code": code,
    }


class _BaseJiangxiNoiseTool(LLMTool):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        function_schema: dict[str, Any],
        client: JiangxiNoiseDataClient | None = None,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="3.1.0",
            requires_context=True,
        )
        self._client = client

    def _get_client(self) -> JiangxiNoiseDataClient:
        if self._client is None:
            self._client = JiangxiNoiseDataClient.from_env()
        return self._client


class QueryJiangxiNoiseCityTool(_BaseJiangxiNoiseTool):
    """Query aggregated city-level Jiangxi noise data over a time range."""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_city",
            "description": (
                "查询江西省城市噪声数据（按功能区汇总）。cities 传江西/江西省/全省时自动查询全部11个地市；"
                "传南昌或南昌市时自动映射城市编码。"
                "注意：本工具返回的是 start_time~end_time 整个时间范围内的城市级聚合值，"
                "每个城市仅 1 条记录，按 4 个功能区（leq_1..leq_4）汇总，"
                "time 字段为“起始时-结束时”的时间范围字符串；不返回逐小时时间序列。"
                "适合全省或多地市的城市对比、整体水平评估。"
                "如需逐小时趋势，请改用 query_jiangxi_noise_station_hour 查询站点小时值。"
                "data_type 对应接口 dataType，可选值 1=审核数据、0=原始数据；默认 1。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["江西省"],
                        "description": "地市或范围数组，如 ['江西省']、['南昌']、['南昌市','赣州市']",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 开始时间，例如 2026-07-30T00:00:00+08:00",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO 8601 结束时间，例如 2026-07-31T00:00:00+08:00",
                    },
                    "data_type": _data_type_schema(DEFAULT_AUDITED_DATA_TYPE),
                    "page_size": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PAGE_SIZE,
                        "default": DEFAULT_PAGE_SIZE,
                    },
                    "max_pages": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_MAX_PAGES,
                        "default": DEFAULT_MAX_PAGES,
                    },
                },
                "required": ["start_time", "end_time"],
                "additionalProperties": False,
            },
        }
        super().__init__(
            name="query_jiangxi_noise_city",
            description="查询江西省城市噪声数据（按功能区汇总）",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        tool_name = self.name
        try:
            city_values = _clean_string_list(cities, "cities")
            resolved_cities, warnings = resolve_city_names(city_values, default_all=True)
            if not resolved_cities:
                raise ToolInputError("missing_cities", "未解析到江西地市，请传江西省或具体地市")
            data_type_value = _resolve_data_type_argument(
                data_type,
                kwargs,
                DEFAULT_AUDITED_DATA_TYPE,
            )
            page_size = _validate_page_size(page_size)
            max_pages = _validate_max_pages(max_pages)
            start, end = _parse_time_range(start_time, end_time)

            records, total_count, pages_fetched, truncated = await _fetch_all_pages(
                self._get_client().query_city_hour_data,
                city_names=resolved_cities,
                start_time=start,
                end_time=end,
                data_type=data_type_value,
                page_size=page_size,
                max_pages=max_pages,
            )
            metadata = {
                "scope": "city",
                "granularity": "range",
                "data_type": data_type_value,
                "data_type_label": DATA_TYPE_LABELS[data_type_value],
                "functional_area_columns": CITY_FUNCTIONAL_AREA_COLUMNS,
                "requested_cities": city_values or ["江西省"],
                "resolved_cities": resolved_cities,
                "resolved_city_codes": [JIANGXI_CITY_CODES[city] for city in resolved_cities],
                "warnings": warnings,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "page_size": page_size,
                "max_pages": max_pages,
            }
            return _success_response(
                tool_name=tool_name,
                records=records,
                total_count=total_count,
                pages_fetched=pages_fetched,
                pagination_truncated=truncated,
                metadata=metadata,
                summary_prefix=(
                    f"江西噪声城市数据查询完成，{start.isoformat()} 至 {end.isoformat()}，"
                    f"{len(resolved_cities)} 个地市"
                ),
                context=context,
            )
        except ToolInputError as exc:
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except JiangxiNoiseClientError as exc:
            logger.warning("jiangxi_noise_city_failed", error_code=exc.code)
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except Exception as exc:
            logger.error("jiangxi_noise_city_unexpected_error", error_type=type(exc).__name__)
            return _error_response(
                tool_name=tool_name,
                code="internal_error",
                message="江西噪声城市数据查询发生内部错误",
            )


class QueryJiangxiNoiseCityComplianceTool(_BaseJiangxiNoiseTool):
    """Query platform-calculated city or province compliance rates."""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_city_compliance",
            "description": (
                "查询江西省城市或全省在自选起止时间内的昼间、夜间噪声达标率。"
                "area_level=city 返回所选地市，area_level=province 返回全省汇总。"
                "统计值由江西噪声平台直接计算，本地不查询日明细、不重新汇总。"
                "仅支持自选时段，不提供月、季、年统计类型参数。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "area_level": {
                        "type": "string",
                        "enum": ["city", "province"],
                        "default": "city",
                        "description": "统计层级：city=城市，province=全省。",
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["江西省"],
                        "description": "城市层级的地市范围，如 ['南昌市']；默认全省11个地市。",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 自选时段开始时间。",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO 8601 自选时段结束时间。",
                    },
                    "data_type": _data_type_schema(DEFAULT_AUDITED_DATA_TYPE),
                },
                "required": ["start_time", "end_time"],
                "additionalProperties": False,
            },
        }
        super().__init__(
            name="query_jiangxi_noise_city_compliance",
            description="查询江西城市或全省任意时段噪声达标率",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        area_level: str = "city",
        cities: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        tool_name = self.name
        try:
            if area_level not in {"city", "province"}:
                raise ToolInputError(
                    "invalid_area_level",
                    "area_level 仅支持 city 或 province",
                )
            city_values = _clean_string_list(cities, "cities")
            resolved_cities, warnings = resolve_city_names(city_values, default_all=True)
            if not resolved_cities:
                raise ToolInputError("missing_cities", "未解析到江西地市")
            data_type_value = _resolve_data_type_argument(
                data_type,
                kwargs,
                DEFAULT_AUDITED_DATA_TYPE,
            )
            start, end = _parse_time_range(start_time, end_time, max_range=None)
            result = await self._get_client().query_area_compliance_data(
                area_level=area_level,
                city_names=resolved_cities,
                start_time=start,
                end_time=end,
                data_type=data_type_value,
            )
            records = result.get("data", [])
            total_count = result.get("total_count", len(records))
            metadata = {
                "scope": area_level,
                "granularity": "custom_range_compliance",
                "calculation_source": "江西噪声平台直接统计，本地未按明细重新计算",
                "data_type": data_type_value,
                "data_type_label": DATA_TYPE_LABELS[data_type_value],
                "requested_cities": city_values or ["江西省"],
                "resolved_cities": resolved_cities,
                "resolved_city_codes": [JIANGXI_CITY_CODES[city] for city in resolved_cities],
                "warnings": warnings,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }
            return _success_response(
                tool_name=tool_name,
                records=records,
                total_count=total_count,
                pages_fetched=1,
                pagination_truncated=False,
                metadata=metadata,
                summary_prefix=(
                    f"江西噪声{area_level}达标率统计完成，"
                    f"{start.isoformat()} 至 {end.isoformat()}"
                ),
                context=context,
            )
        except ToolInputError as exc:
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except JiangxiNoiseClientError as exc:
            logger.warning("jiangxi_noise_area_compliance_failed", error_code=exc.code)
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except Exception as exc:
            logger.error(
                "jiangxi_noise_area_compliance_unexpected_error",
                error_type=type(exc).__name__,
            )
            return _error_response(
                tool_name=tool_name,
                code="internal_error",
                message="江西噪声城市/全省达标率查询发生内部错误",
            )


class _BaseJiangxiNoiseStationTool(_BaseJiangxiNoiseTool):
    granularity: str
    supports_data_type: bool = False
    default_data_type: int = DEFAULT_ORIGINAL_DATA_TYPE
    enforce_time_range_limit: bool = True

    async def _execute_station_query(
        self,
        *,
        context: ExecutionContext | None,
        cities: list[str] | None,
        stations: list[str] | None,
        station_codes: list[str] | None,
        start_time: str,
        end_time: str,
        data_type: Any,
        page_size: int,
        max_pages: int,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool_name = self.name
        try:
            city_values = _clean_string_list(cities, "cities")
            station_values = _clean_string_list(stations, "stations")
            code_values = _clean_string_list(station_codes, "station_codes")
            resolved_stations, resolution_metadata, warnings = resolve_station_records(
                cities=city_values,
                stations=station_values,
                station_codes=code_values,
                default_all=False,
            )
            if not resolved_stations:
                raise ToolInputError(
                    "missing_station_scope",
                    "站点查询必须提供 cities、stations 或 station_codes；cities 可传江西省、南昌等",
                )
            data_type_value = _resolve_data_type_argument(
                data_type,
                extra_kwargs or {},
                self.default_data_type,
            )
            page_size = _validate_page_size(page_size)
            max_pages = _validate_max_pages(max_pages)
            start, end = _parse_time_range(
                start_time,
                end_time,
                max_range=MAX_QUERY_RANGE if self.enforce_time_range_limit else None,
            )
            client = self._get_client()
            if self.granularity == "minute":
                query = client.query_station_minute_data
            elif self.granularity == "hour":
                query = client.query_station_hour_data
            elif self.granularity == "day":
                query = client.query_station_day_data
            elif self.granularity == "compliance":
                query = client.query_station_compliance_data
            else:
                query = client.query_station_statistics_data
            records, total_count, pages_fetched, truncated = await _fetch_all_pages(
                query,
                station_codes=[station.station_code for station in resolved_stations],
                start_time=start,
                end_time=end,
                data_type=data_type_value,
                page_size=page_size,
                max_pages=max_pages,
            )
            records = _attach_station_directory_fields(records, resolved_stations)
            stations_metadata = _station_static_metadata(records)
            records = _strip_station_static_fields(records)
            metadata = {
                "scope": "station",
                "granularity": self.granularity,
                "functional_area_mapping": _station_functional_area_mapping_metadata(),
                "warnings": warnings,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "page_size": page_size,
                "max_pages": max_pages,
                "stations": stations_metadata,
                **resolution_metadata,
            }
            if self.supports_data_type:
                metadata["data_type"] = data_type_value
                metadata["data_type_label"] = DATA_TYPE_LABELS[data_type_value]
            if self.granularity == "compliance":
                metadata["calculation_source"] = (
                    "江西噪声平台直接统计，本地未按日明细重新计算"
                )
            granularity_label = {
                "minute": "分钟",
                "hour": "小时",
                "day": "日均",
                "statistics": "统计",
                "compliance": "周期达标率",
            }.get(self.granularity, self.granularity)
            return _success_response(
                tool_name=tool_name,
                records=records,
                total_count=total_count,
                pages_fetched=pages_fetched,
                pagination_truncated=truncated,
                metadata=metadata,
                summary_prefix=(
                    f"江西噪声站点{granularity_label}数据查询完成，"
                    f"{start.isoformat()} 至 {end.isoformat()}，{len(resolved_stations)} 个站点"
                ),
                context=context,
            )
        except ToolInputError as exc:
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except JiangxiNoiseClientError as exc:
            logger.warning(
                "jiangxi_noise_station_query_failed",
                tool_name=tool_name,
                error_code=exc.code,
            )
            return _error_response(tool_name=tool_name, code=exc.code, message=exc.message)
        except Exception as exc:
            logger.error(
                "jiangxi_noise_station_query_unexpected_error",
                tool_name=tool_name,
                error_type=type(exc).__name__,
            )
            return _error_response(
                tool_name=tool_name,
                code="internal_error",
                message="江西噪声站点数据查询发生内部错误",
            )


def _station_parameters_schema(
    granularity_label: str,
    *,
    data_type_default: int | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "cities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "地市或范围数组，如 ['江西省']、['南昌']。传地市会自动展开下辖全部噪声站点。",
        },
        "stations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "站点名称数组，支持完整站点名或名称片段，如 ['东湖区大院街道']。",
        },
        "station_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "站点编码数组，如 ['1737A']。",
        },
        "start_time": {
            "type": "string",
            "description": "ISO 8601 开始时间，例如 2026-07-30T00:00:00+08:00",
        },
        "end_time": {
            "type": "string",
            "description": "ISO 8601 结束时间，例如 2026-07-31T00:00:00+08:00",
        },
        "page_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_PAGE_SIZE,
            "default": DEFAULT_PAGE_SIZE,
        },
        "max_pages": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_MAX_PAGES,
            "default": DEFAULT_MAX_PAGES,
        },
    }
    if data_type_default is not None:
        properties["data_type"] = _data_type_schema(data_type_default)

    return {
        "type": "object",
        "properties": properties,
        "required": ["start_time", "end_time"],
        "additionalProperties": False,
        "description": granularity_label,
    }


class QueryJiangxiNoiseStationMinuteTool(_BaseJiangxiNoiseStationTool):
    """Query station-level 1-minute Jiangxi noise data."""

    granularity = "minute"

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_station_minute",
            "description": (
                "查询江西省站点1分钟噪声数据。cities 传江西/江西省/全省时自动展开全部已归属站点；"
                "传南昌或南昌市时自动展开南昌下辖噪声站点；也可传站点名称或编码。"
                "data 每条仅保留 station_code/time/指标，站点名称、城市、经纬度和功能区见 metadata.stations。"
                "分钟数据量较大，优先缩小时间范围或站点范围。"
            ),
            "parameters": _station_parameters_schema("站点1分钟噪声查询参数"),
        }
        super().__init__(
            name="query_jiangxi_noise_station_minute",
            description="查询江西省站点1分钟噪声数据，返回站点功能区语义映射",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._execute_station_query(
            context=context,
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            page_size=page_size,
            max_pages=max_pages,
            extra_kwargs=kwargs,
        )


class QueryJiangxiNoiseStationHourTool(_BaseJiangxiNoiseStationTool):
    """Query station-level hourly Jiangxi noise data."""

    granularity = "hour"
    supports_data_type = True
    default_data_type = DEFAULT_AUDITED_DATA_TYPE

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_station_hour",
            "description": (
                "查询江西省站点小时噪声数据。cities 传江西/江西省/全省时自动展开全部已归属站点；"
                "传南昌或南昌市时自动展开南昌下辖噪声站点；也可传站点名称或编码。"
                "data 每条仅保留 station_code/time/指标，站点名称、城市、经纬度和功能区见 metadata.stations。"
                "data_type 对应接口 dataType，可选值 1=审核数据、0=原始数据；默认 1。"
            ),
            "parameters": _station_parameters_schema(
                "站点小时噪声查询参数",
                data_type_default=DEFAULT_AUDITED_DATA_TYPE,
            ),
        }
        super().__init__(
            name="query_jiangxi_noise_station_hour",
            description="查询江西省站点小时噪声数据，返回站点功能区语义映射",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._execute_station_query(
            context=context,
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            page_size=page_size,
            max_pages=max_pages,
            extra_kwargs=kwargs,
        )


class QueryJiangxiNoiseStationStatisticsTool(_BaseJiangxiNoiseStationTool):
    """Query station-level period statistics Jiangxi noise data."""

    granularity = "statistics"
    enforce_time_range_limit = False

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_station_statistics",
            "description": (
                "查询江西省站点任意时段统计噪声数据。cities 传江西/江西省/全省时自动展开全部已归属站点；"
                "传南昌或南昌市时自动展开南昌下辖噪声站点；也可传站点名称或编码。"
                "返回每个站点在查询时段内聚合的统计指标（非逐日均值）：ldn 昼夜等效声级、ld 昼间等效声级、"
                "ln 夜间等效声级、l5/l10/l50/l90/l95 统计声级、lMin/lMax、sd 标准偏差、"
                "超标标志 isLdOverStandard/isLnOverStandard，以及车流量与气象辅助指标。"
                "本工具不限查询时间范围，可查询半年、全年等长周期统计数据。"
            ),
            "parameters": _station_parameters_schema("站点统计噪声查询参数"),
        }
        super().__init__(
            name="query_jiangxi_noise_station_statistics",
            description="查询江西省站点任意时段统计噪声数据，返回时段聚合统计指标",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._execute_station_query(
            context=context,
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            page_size=page_size,
            max_pages=max_pages,
            extra_kwargs=kwargs,
        )


class QueryJiangxiNoiseStationComplianceTool(_BaseJiangxiNoiseStationTool):
    """Query platform-calculated station compliance rates for a custom range."""

    granularity = "compliance"
    supports_data_type = True
    default_data_type = DEFAULT_AUDITED_DATA_TYPE
    enforce_time_range_limit = False

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_station_compliance",
            "description": (
                "查询江西省噪声站点在自选起止时间内的昼间、夜间达标率。"
                "可按地市、站点名称或站点编码选择范围；统计值由江西噪声平台直接计算，"
                "本地不查询日明细、不重新汇总。仅支持自选时段，不提供月、季、年统计类型参数。"
            ),
            "parameters": _station_parameters_schema(
                "站点自选时段达标率查询参数",
                data_type_default=DEFAULT_AUDITED_DATA_TYPE,
            ),
        }
        super().__init__(
            name="query_jiangxi_noise_station_compliance",
            description="查询江西噪声站点任意时段昼夜达标率",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._execute_station_query(
            context=context,
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            page_size=page_size,
            max_pages=max_pages,
            extra_kwargs=kwargs,
        )


class QueryJiangxiNoiseStationDayTool(_BaseJiangxiNoiseStationTool):
    """Query station-level daily Jiangxi noise data."""

    granularity = "day"
    supports_data_type = True
    default_data_type = DEFAULT_AUDITED_DATA_TYPE
    enforce_time_range_limit = False

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "query_jiangxi_noise_station_day",
            "description": (
                "查询江西省站点日均噪声数据。cities 传江西/江西省/全省时自动展开全部已归属站点；"
                "传南昌或南昌市时自动展开南昌下辖噪声站点；也可传站点名称或编码。"
                "data 每条仅保留 station_code/time/指标，站点名称、城市、经纬度和功能区见 metadata.stations。"
                "data_type 对应接口 dataType，可选值 1=审核数据、0=原始数据；默认 1。"
                "本工具不限查询时间范围，可查询半年、全年等长周期日均值。"
            ),
            "parameters": _station_parameters_schema(
                "站点日均噪声查询参数",
                data_type_default=DEFAULT_AUDITED_DATA_TYPE,
            ),
        }
        super().__init__(
            name="query_jiangxi_noise_station_day",
            description="查询江西省站点日均噪声数据，返回站点功能区语义映射",
            function_schema=function_schema,
            client=client,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        cities: list[str] | None = None,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        data_type: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._execute_station_query(
            context=context,
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            page_size=page_size,
            max_pages=max_pages,
            extra_kwargs=kwargs,
        )
