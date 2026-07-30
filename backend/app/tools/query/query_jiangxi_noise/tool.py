"""江西省噪声监测数据 LLM 查询工具。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JIANGXI_CITY_CODES,
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
    normalize_to_shanghai,
    resolve_city_codes,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

MAX_QUERY_RANGE = timedelta(days=30)
STATION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
REVIEW_STATUS_DATA_TYPE = {"raw": 0, "audited": 1}


class ToolInputError(ValueError):
    """工具输入错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _deduplicate(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


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
            f"{field_name} 必须使用 ISO 8601 格式",
        ) from exc
    return normalize_to_shanghai(parsed)


def _parse_time_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    start = _parse_time(start_time, "start_time")
    end = _parse_time(end_time, "end_time")
    if start > end:
        raise ToolInputError("invalid_time_range", "start_time 不能晚于 end_time")
    if end - start > MAX_QUERY_RANGE:
        raise ToolInputError("time_range_too_large", "单次查询时间范围不能超过 30 天")
    return start, end


def _validate_station_codes(station_codes: Any) -> list[str]:
    if not isinstance(station_codes, list) or not station_codes:
        raise ToolInputError("missing_station_codes", "站点查询必须提供 station_codes")
    normalized: list[str] = []
    for raw_code in station_codes:
        if not isinstance(raw_code, str):
            raise ToolInputError("invalid_station_code", "站点代码必须是字符串")
        code = raw_code.strip()
        if not code or not STATION_CODE_PATTERN.fullmatch(code):
            raise ToolInputError("invalid_station_code", f"无效的站点代码：{raw_code}")
        normalized.append(code)
    return _deduplicate(normalized)


def _validate_city_names(city_names: Any) -> list[str]:
    if not isinstance(city_names, list) or not city_names:
        raise ToolInputError("missing_city_names", "城市查询必须提供 city_names")
    normalized: list[str] = []
    for raw_name in city_names:
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ToolInputError("invalid_city", "城市名称或代码不能为空")
        normalized.append(raw_name.strip())
    try:
        resolve_city_codes(normalized)
    except JiangxiNoiseClientError as exc:
        raise ToolInputError(exc.code, exc.message) from exc
    return _deduplicate(normalized)


class GetJiangxiNoiseDataTool(LLMTool):
    """查询江西省站点小时、站点日均和城市小时噪声数据。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        common_properties = {
            "review_status": {
                "type": "string",
                "enum": ["raw", "audited"],
                "default": "raw",
                "description": "raw=原始数据，audited=审核数据",
            },
            "start_time": {
                "type": "string",
                "description": "ISO 8601 开始时间，例如 2026-07-27T00:00:00+08:00",
            },
            "end_time": {
                "type": "string",
                "description": "ISO 8601 结束时间，例如 2026-07-28T00:00:00+08:00",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 50,
                "description": "最多返回记录数，默认50，最大100",
            },
        }
        function_schema = {
            "name": "get_jiangxi_noise_data",
            "description": (
                "查询江西省噪声监测数据。支持站点小时值、站点日均值和城市小时聚合值；"
                "城市日均接口暂未开放。无时区时间按北京时间解释，单次范围不超过30天。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "站点噪声查询",
                        "type": "object",
                        "properties": {
                            **common_properties,
                            "scope": {"const": "station"},
                            "granularity": {
                                "type": "string",
                                "enum": ["hour", "day"],
                            },
                            "station_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "站点代码列表，例如 1737A",
                            },
                        },
                        "required": [
                            "scope",
                            "granularity",
                            "station_codes",
                            "start_time",
                            "end_time",
                        ],
                        "additionalProperties": False,
                    },
                    {
                        "title": "城市小时噪声查询",
                        "type": "object",
                        "properties": {
                            **common_properties,
                            "scope": {"const": "city"},
                            "granularity": {"const": "hour"},
                            "city_names": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": (
                                    "城市名称或6位城市代码列表。支持："
                                    + "、".join(JIANGXI_CITY_CODES.keys())
                                ),
                            },
                        },
                        "required": [
                            "scope",
                            "granularity",
                            "city_names",
                            "start_time",
                            "end_time",
                        ],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_data",
            description="查询江西省噪声监测数据",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=False,
        )
        self._client = client

    def _get_client(self) -> JiangxiNoiseDataClient:
        if self._client is None:
            self._client = JiangxiNoiseDataClient.from_env()
        return self._client

    @staticmethod
    def _validate_mode(scope: str, granularity: str, review_status: str) -> int:
        if scope not in {"station", "city"}:
            raise ToolInputError("invalid_scope", "scope 必须是 station 或 city")
        if granularity not in {"hour", "day"}:
            raise ToolInputError("invalid_granularity", "granularity 必须是 hour 或 day")
        if scope == "city" and granularity == "day":
            raise ToolInputError(
                "unsupported_city_day",
                "城市日均接口暂未开放，请等待平台提供准确信息",
            )
        if review_status not in REVIEW_STATUS_DATA_TYPE:
            raise ToolInputError(
                "invalid_review_status",
                "review_status 必须是 raw 或 audited",
            )
        return REVIEW_STATUS_DATA_TYPE[review_status]

    @staticmethod
    def _validate_max_results(max_results: Any) -> int:
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 100
        ):
            raise ToolInputError("invalid_max_results", "max_results 必须是 1 至 100 的整数")
        return max_results

    async def execute(
        self,
        context: ExecutionContext | None = None,
        scope: str = "",
        granularity: str = "",
        review_status: str = "raw",
        station_codes: list[str] | None = None,
        city_names: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        max_results: int = 50,
    ) -> dict[str, Any]:
        del context
        try:
            data_type = self._validate_mode(scope, granularity, review_status)
            limit = self._validate_max_results(max_results)
            start, end = _parse_time_range(start_time, end_time)
            if scope == "station" and city_names:
                raise ToolInputError(
                    "conflicting_locations",
                    "站点查询不能同时提供 city_names",
                )
            if scope == "city" and station_codes:
                raise ToolInputError(
                    "conflicting_locations",
                    "城市查询不能同时提供 station_codes",
                )
            client = self._get_client()

            if scope == "station":
                codes = _validate_station_codes(station_codes)
                query = (
                    client.query_station_hour_data
                    if granularity == "hour"
                    else client.query_station_day_data
                )
                result = await query(
                    station_codes=codes,
                    start_time=start,
                    end_time=end,
                    data_type=data_type,
                    max_result_count=limit,
                )
            else:
                cities = _validate_city_names(city_names)
                result = await client.query_city_hour_data(
                    city_names=cities,
                    start_time=start,
                    end_time=end,
                    data_type=data_type,
                    max_result_count=limit,
                )

            raw_data = result.get("data", [])
            data = raw_data[:limit] if isinstance(raw_data, list) else []
            total_count = result.get("total_count", len(data))
            if not isinstance(total_count, int):
                total_count = len(data)
            truncated = total_count > len(data)
            response: dict[str, Any] = {
                "success": True,
                "scope": scope,
                "granularity": granularity,
                "review_status": review_status,
                "data": data,
                "count": len(data),
                "total_count": total_count,
                "truncated": truncated,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }
            if truncated:
                response["hint"] = "结果已截断，请缩小时间范围或地点范围后继续查询"
            logger.info(
                "jiangxi_noise_query_success",
                scope=scope,
                granularity=granularity,
                count=len(data),
                total_count=total_count,
            )
            return response
        except ToolInputError as exc:
            return {"success": False, "error_code": exc.code, "error": exc.message}
        except JiangxiNoiseClientError as exc:
            logger.warning("jiangxi_noise_query_failed", error_code=exc.code)
            return {"success": False, "error_code": exc.code, "error": exc.message}
        except Exception as exc:
            logger.error(
                "jiangxi_noise_query_unexpected_error",
                error_type=type(exc).__name__,
            )
            return {
                "success": False,
                "error_code": "internal_error",
                "error": "江西噪声数据查询发生内部错误",
            }

    def get_description(self) -> str:
        return self.description
