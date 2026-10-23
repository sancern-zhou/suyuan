"""江西噪声数据工具共享输入校验、枚举映射与结果封装。

语义口径（与平台服务端实现对齐）：
- 昼间 Ld：06:00–22:00；夜间 Ln：22:00–06:00。
- review_status raw=原始数据(0)、audited=审核数据(1)。
- 数值型缺测以 -99 表示；显示型缺测为占位字符串。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.external_apis.jiangxi_noise_api_client import (
    JiangxiNoiseClientError,
    normalize_to_shanghai,
)

STATION_CODE_PATTERN_STR = r"^[A-Za-z0-9_-]+$"
DEFAULT_MAX_RESULTS = 50
MAX_RESULTS_LIMIT = 100

# GetNoiseEvaluateInput.TimeType（TimeType 枚举）
EVALUATE_TIME_TYPE = {"day": 30, "month": 40, "quarter": 45, "year": 55, "any_range": 100}
# FunEvaluation ReportTimeType
FUN_REPORT_TIME_TYPE = {
    "hour": 1,
    "day": 2,
    "week": 3,
    "month": 4,
    "quarter": 5,
    "half_year": 6,
    "year": 7,
    "any_range": 8,
}
# NoiseRegionType：站点0/区县1/城市2/省份3
REGION_TYPE = {"district": 1, "city": 2, "province": 3}
# AnalysisDimension：市1/区县2/站点3
SOURCE_DIMENSION = {"city": 1, "district": 2, "station": 3}
# NoiseYearOnYearDimension / NoiseYearOnYearIndicator
YOY_DIMENSION = {"city": 1, "station": 2}
YOY_INDICATOR = {"ld": 1, "ln": 2, "day_qualified_rate": 3, "night_qualified_rate": 4}
# NoisePeriodType
PERIOD_TYPE = {"month": 1, "quarter": 2}
# NoiseLongTermTimeScale
LONG_TERM_SCALE = {"month": 1, "quarter": 2, "year": 3}
# NoiseCompareDimension / NoiseCompareTimeGranularity
COMPARE_DIMENSION = {"city": 1, "function_area": 2, "station": 3}
COMPARE_GRANULARITY = {"hour": 1, "day": 2, "month": 3, "year": 4}
# 联网概况：NetworkStatus / AirDetailSrcDataType / 分钟2小时3
NETWORK_STATUS = {"all": 0, "offline": 1, "online": 2}
NETWORK_DATA_TYPE = {"minute": 2, "hour": 3}
RECEIVING_RATE_TYPE = {"receiving": 0, "effective": 1}
# GetNoiseEventDto.TimeType（类型占比接口只处理日/月/季/年）
EVENT_TIME_TYPE = {"day": 30, "month": 40, "quarter": 45, "year": 55}

REVIEW_STATUS_DATA_TYPE = {"raw": 0, "audited": 1}


class ToolInputError(ValueError):
    """工具输入错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def from_client_error(exc: JiangxiNoiseClientError) -> ToolInputError:
    return ToolInputError(exc.code, exc.message)


def parse_datetime_param(value: Any, field_name: str) -> datetime:
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
            f"{field_name} 必须使用 ISO 8601 格式，例如 2026-07-27T00:00:00+08:00",
        ) from exc
    return normalize_to_shanghai(parsed)


def parse_time_range(
    start_time: Any,
    end_time: Any,
    *,
    max_span: timedelta,
    field_start: str = "start_time",
    field_end: str = "end_time",
) -> tuple[datetime, datetime]:
    start = parse_datetime_param(start_time, field_start)
    end = parse_datetime_param(end_time, field_end)
    if start > end:
        raise ToolInputError("invalid_time_range", f"{field_start} 不能晚于 {field_end}")
    if end - start > max_span:
        limit_days = max_span.days
        raise ToolInputError(
            "time_range_too_large",
            f"单次查询时间范围不能超过 {limit_days} 天",
        )
    return start, end


def platform_time(value: datetime) -> str:
    """平台时间格式：本地时间字符串，无需时区后缀。"""
    return normalize_to_shanghai(value).strftime("%Y-%m-%d %H:%M:%S")


def require_enum(value: Any, mapping: dict[str, Any], field_name: str) -> Any:
    if not isinstance(value, str) or value not in mapping:
        options = "、".join(mapping.keys())
        raise ToolInputError(
            f"invalid_{field_name}",
            f"{field_name} 必须是：{options}",
        )
    return mapping[value]


def require_code_list(
    values: Any,
    field_name: str,
    *,
    max_count: int = 50,
    allow_empty: bool = False,
) -> list[str]:
    import re

    if values is None:
        if allow_empty:
            return []
        raise ToolInputError(f"missing_{field_name}", f"必须提供 {field_name}")
    if not isinstance(values, list):
        raise ToolInputError(f"invalid_{field_name}", f"{field_name} 必须是字符串数组")
    normalized: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(STATION_CODE_PATTERN_STR)
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise ToolInputError(f"invalid_{field_name}", f"{field_name} 存在空值")
        code = raw.strip()
        if not pattern.fullmatch(code):
            raise ToolInputError(f"invalid_{field_name}", f"无效编码：{raw}")
        if code not in seen:
            seen.add(code)
            normalized.append(code)
    if not normalized and not allow_empty:
        raise ToolInputError(f"missing_{field_name}", f"必须提供 {field_name}")
    if len(normalized) > max_count:
        raise ToolInputError(
            f"invalid_{field_name}",
            f"{field_name} 一次最多 {max_count} 个",
        )
    return normalized


def optional_code_list(values: Any, field_name: str) -> list[str]:
    if values is None:
        return []
    return require_code_list(values, field_name, allow_empty=True)


def validate_max_results(max_results: Any) -> int:
    if (
        isinstance(max_results, bool)
        or not isinstance(max_results, int)
        or not 1 <= max_results <= MAX_RESULTS_LIMIT
    ):
        raise ToolInputError(
            "invalid_max_results",
            f"max_results 必须是 1 至 {MAX_RESULTS_LIMIT} 的整数",
        )
    return max_results


def array_query_params(name: str, values: list[str]) -> dict[str, str]:
    return {f"{name}[{index}]": value for index, value in enumerate(values)}


def list_response(
    *,
    variant: str,
    result: dict[str, Any],
    limit: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_data = result.get("data", [])
    data = raw_data[:limit] if isinstance(raw_data, list) else []
    total_count = result.get("total_count", len(data))
    if not isinstance(total_count, int):
        total_count = len(data)
    response: dict[str, Any] = {
        "success": True,
        "data": data,
        "count": len(data),
        "total_count": total_count,
        "truncated": total_count > len(data),
    }
    if extra:
        response.update(extra)
    if response["truncated"]:
        response["hint"] = (
            f"结果已截断（共 {total_count} 条，返回前 {len(data)} 条），"
            "请缩小时间或范围后继续查询"
        )
    return response


def object_response(
    *,
    variant: str,
    result: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = result.get("data")
    response: dict[str, Any] = {
        "success": True,
        "data": data,
    }
    response.update(extra)
    return response


def tool_error_response(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ToolInputError):
        return {"success": False, "error_code": exc.code, "error": exc.message}
    if isinstance(exc, JiangxiNoiseClientError):
        return {"success": False, "error_code": exc.code, "error": exc.message}
    return {
        "success": False,
        "error_code": "internal_error",
        "error": "江西噪声数据查询发生内部错误",
    }


def build_common_time_properties(max_days_note: str) -> dict[str, Any]:
    return {
        "start_time": {
            "type": "string",
            "description": f"ISO 8601 开始时间，例如 2026-07-01T00:00:00+08:00。{max_days_note}",
        },
        "end_time": {
            "type": "string",
            "description": "ISO 8601 结束时间，例如 2026-07-02T00:00:00+08:00",
        },
    }
