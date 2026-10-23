"""江西省噪声监测数据 LLM 查询工具（秒/分/时/日/月/季/年多粒度）。"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JIANGXI_CITY_CODES,
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
    resolve_city_codes,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    EVALUATE_TIME_TYPE,
    REVIEW_STATUS_DATA_TYPE,
    ToolInputError,
    array_query_params,
    list_response,
    parse_time_range,
    platform_time,
    require_code_list,
    tool_error_response,
    validate_max_results,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

MAX_QUERY_RANGE = timedelta(days=30)
MINUTE_QUERY_RANGE = timedelta(days=3)
SECOND_QUERY_RANGE = timedelta(hours=2)
PERIOD_REPORT_RANGE = timedelta(days=1100)
STATION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

GRANULARITY_NOTES = {
    "second": "秒级瞬时原始数据（数据量大，单次不超过2小时，建议1个站点）",
    "minute": "分钟值（单次不超过3天）",
    "hour": "小时值（单次不超过30天）",
    "day": "日均值（含Ld/Ln/Ldn，单次不超过30天）",
    "month": "月报表（按月汇总）",
    "quarter": "季报表（按季度汇总）",
    "year": "年报表（按年汇总）",
}

# 月/季/年报走 DATStationDay 月季年接口（TimeType 枚举：月40/季45/年55）
PERIOD_REPORT_TIME_TYPE = {
    "month": EVALUATE_TIME_TYPE["month"],
    "quarter": EVALUATE_TIME_TYPE["quarter"],
    "year": EVALUATE_TIME_TYPE["year"],
}


class GetJiangxiNoiseDataTool(LLMTool):
    """查询江西省噪声监测数据（站点秒/分/时/日/月/季/年、城市小时、区县日值）。"""

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
                "description": "ISO 8601 开始时间，例如 2026-07-01T00:00:00+08:00",
            },
            "end_time": {
                "type": "string",
                "description": "ISO 8601 结束时间，例如 2026-07-02T00:00:00+08:00",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 50,
                "description": "最多返回记录数，默认50，最大100",
            },
        }
        station_granularity = {
            "type": "string",
            "enum": list(GRANULARITY_NOTES.keys()),
            "description": "时间粒度：" + "；".join(
                f"{key}={note}" for key, note in GRANULARITY_NOTES.items()
            ),
        }
        function_schema = {
            "name": "get_jiangxi_noise_data",
            "description": (
                "查询江西省噪声监测平台数据。"
                "站点维度支持秒级瞬时、分钟值、小时值、日均值、月/季/年报表；"
                "城市维度支持城市小时功能区聚合值；区县维度支持区县日值。"
                "数据含等效声级Leq、昼夜声级Ld/Ln/Ldn、累计百分声级L5~L95、"
                "采集率DAR/VDR、气象量与车流量。"
                "缺测或无效值以-99或占位字符串表示。"
                "站点编码可先用 get_jiangxi_noise_directory 查询；"
                "无时区时间按北京时间解释。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "站点噪声数据",
                        "type": "object",
                        "properties": {
                            **common_properties,
                            "scope": {"const": "station"},
                            "granularity": station_granularity,
                            "station_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": (
                                    "站点编码列表，例如 1737A。"
                                    "秒级数据建议只传1个站点"
                                ),
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
                    {
                        "title": "区县日值查询",
                        "type": "object",
                        "properties": {
                            **common_properties,
                            "scope": {"const": "district"},
                            "granularity": {"const": "day"},
                            "district_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": (
                                    "区县编码列表（6位行政区划码，如 360102），"
                                    "可用 get_jiangxi_noise_directory 查询"
                                ),
                            },
                        },
                        "required": [
                            "scope",
                            "granularity",
                            "district_codes",
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
            description="查询江西省噪声监测数据（站点多粒度/城市/区县）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="3.0.0",
            requires_context=False,
        )
        self._client = client

    def _get_client(self) -> JiangxiNoiseDataClient:
        if self._client is None:
            self._client = JiangxiNoiseDataClient.from_env()
        return self._client

    @staticmethod
    def _resolve_mode(
        scope: str,
        granularity: str,
        review_status: str,
    ) -> tuple[int, timedelta]:
        if scope not in {"station", "city", "district"}:
            raise ToolInputError(
                "invalid_scope",
                "scope 必须是 station、city 或 district",
            )
        if granularity not in GRANULARITY_NOTES:
            raise ToolInputError(
                "invalid_granularity",
                "granularity 必须是：" + "、".join(GRANULARITY_NOTES.keys()),
            )
        if scope == "city" and granularity != "hour":
            raise ToolInputError(
                "invalid_granularity",
                "城市查询的 granularity 只能是 hour",
            )
        if scope == "district" and granularity != "day":
            raise ToolInputError(
                "invalid_granularity",
                "区县查询的 granularity 只能是 day",
            )
        if review_status not in REVIEW_STATUS_DATA_TYPE:
            raise ToolInputError(
                "invalid_review_status",
                "review_status 必须是 raw 或 audited",
            )
        if granularity == "second":
            return REVIEW_STATUS_DATA_TYPE[review_status], SECOND_QUERY_RANGE
        if granularity == "minute":
            return REVIEW_STATUS_DATA_TYPE[review_status], MINUTE_QUERY_RANGE
        if granularity in {"month", "quarter", "year"}:
            return REVIEW_STATUS_DATA_TYPE[review_status], PERIOD_REPORT_RANGE
        return REVIEW_STATUS_DATA_TYPE[review_status], MAX_QUERY_RANGE

    async def _query_station(
        self,
        client: JiangxiNoiseDataClient,
        codes: list[str],
        start,
        end,
        data_type: int,
        granularity: str,
        limit: int,
    ) -> dict[str, Any]:
        if granularity == "hour":
            return await client.query_station_hour_data(
                station_codes=codes,
                start_time=start,
                end_time=end,
                data_type=data_type,
                max_result_count=limit,
            )
        if granularity == "day":
            return await client.query_station_day_data(
                station_codes=codes,
                start_time=start,
                end_time=end,
                data_type=data_type,
                max_result_count=limit,
            )
        if granularity in PERIOD_REPORT_TIME_TYPE:
            params: dict[str, Any] = {
                "skipCount": 0,
                "maxResultCount": limit,
                "dataType": data_type,
                "timeType": PERIOD_REPORT_TIME_TYPE[granularity],
                "timepoint[0]": platform_time(start),
                "timepoint[1]": platform_time(end),
            }
            params.update(array_query_params("codes", codes))
            return await client.query_platform_api("station_period_report", params=params)
        if granularity == "minute":
            params = {
                "skipCount": 0,
                "maxResultCount": limit,
                "dataType": data_type,
                "timePoint[0]": platform_time(start),
                "timePoint[1]": platform_time(end),
            }
            params.update(array_query_params("codes", codes))
            return await client.query_platform_api("station_minute", params=params)
        # 秒级瞬时：NoiseBaseData，参数为 stationCodes
        params = {
            "skipCount": 0,
            "maxResultCount": limit,
            "dataType": data_type,
            "isMark": 0,
            "timePoint[0]": platform_time(start),
            "timePoint[1]": platform_time(end),
        }
        params.update(array_query_params("stationCodes", codes))
        return await client.query_platform_api("station_second", params=params)

    async def execute(
        self,
        context: ExecutionContext | None = None,
        scope: str = "",
        granularity: str = "",
        review_status: str = "raw",
        station_codes: list[str] | None = None,
        city_names: list[str] | None = None,
        district_codes: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        max_results: int = 50,
    ) -> dict[str, Any]:
        del context
        try:
            data_type, max_span = self._resolve_mode(scope, granularity, review_status)
            limit = validate_max_results(max_results)
            start, end = parse_time_range(start_time, end_time, max_span=max_span)
            client = self._get_client()
            extra = {
                "scope": scope,
                "granularity": granularity,
                "review_status": review_status,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }

            if scope == "station":
                if city_names or district_codes:
                    raise ToolInputError(
                        "conflicting_locations",
                        "站点查询不能同时提供 city_names 或 district_codes",
                    )
                codes = require_code_list(station_codes, "station_codes")
                result = await self._query_station(
                    client, codes, start, end, data_type, granularity, limit
                )
            elif scope == "city":
                if station_codes or district_codes:
                    raise ToolInputError(
                        "conflicting_locations",
                        "城市查询不能同时提供 station_codes 或 district_codes",
                    )
                try:
                    cities = resolve_city_codes(
                        [name.strip() for name in (city_names or []) if isinstance(name, str)]
                    )
                except JiangxiNoiseClientError as exc:
                    raise ToolInputError(exc.code, exc.message) from exc
                if not city_names:
                    raise ToolInputError("missing_city_names", "必须提供 city_names")
                result = await client.query_city_hour_data(
                    city_names=[name.strip() for name in city_names],
                    start_time=start,
                    end_time=end,
                    data_type=data_type,
                    max_result_count=limit,
                )
            else:
                if station_codes or city_names:
                    raise ToolInputError(
                        "conflicting_locations",
                        "区县查询不能同时提供 station_codes 或 city_names",
                    )
                codes = require_code_list(district_codes, "district_codes")
                params: dict[str, Any] = {
                    "skipCount": 0,
                    "maxResultCount": limit,
                    "dataType": data_type,
                    "sandType": 0,
                    "timePoint[0]": platform_time(start),
                    "timePoint[1]": platform_time(end),
                }
                params.update(array_query_params("codes", codes))
                result = await client.query_platform_api("district_day", params=params)

            response = list_response(variant=granularity, result=result, limit=limit, extra=extra)
            logger.info(
                "jiangxi_noise_query_success",
                scope=scope,
                granularity=granularity,
                count=response.get("count"),
                total_count=response.get("total_count"),
            )
            return response
        except (ToolInputError, JiangxiNoiseClientError) as exc:
            if isinstance(exc, JiangxiNoiseClientError):
                logger.warning("jiangxi_noise_query_failed", error_code=exc.code)
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_query_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
