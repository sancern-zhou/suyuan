"""江西省噪声趋势对比 LLM 查询工具。

覆盖平台趋势分析域：年度同比、月/季度环比、24小时趋势、长期均值趋势、
城市/功能区/站点多对象对比。
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    COMPARE_DIMENSION,
    COMPARE_GRANULARITY,
    LONG_TERM_SCALE,
    PERIOD_TYPE,
    REVIEW_STATUS_DATA_TYPE,
    ToolInputError,
    YOY_DIMENSION,
    YOY_INDICATOR,
    optional_code_list,
    parse_datetime_param,
    parse_time_range,
    platform_time,
    require_code_list,
    require_enum,
    tool_error_response,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

COMPARE_RANGE = timedelta(days=370)
LONG_TERM_RANGE = timedelta(days=1150)


class GetJiangxiNoiseTrendsTool(LLMTool):
    """查询江西省噪声趋势对比分析数据。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        dimension_prop = {
            "type": "string",
            "enum": ["city", "station"],
            "description": "对比维度：city=按城市、station=按站点",
        }
        indicator_prop = {
            "type": "string",
            "enum": ["ld", "ln", "day_qualified_rate", "night_qualified_rate"],
            "description": (
                "分析指标：ld=昼间等效声级、ln=夜间等效声级、"
                "day_qualified_rate=昼间达标率、night_qualified_rate=夜间达标率"
            ),
        }
        data_type_prop = {
            "type": "string",
            "enum": ["raw", "audited"],
            "default": "raw",
            "description": "raw=原始数据，audited=审核数据",
        }
        function_schema = {
            "name": "get_jiangxi_noise_trends",
            "description": (
                "查询江西省噪声趋势对比分析。支持：年度同比（基准年 vs 两个对比年）、"
                "月度/季度环比、单站点24小时趋势（监测日 vs 对比日，07:00至次日06:00）、"
                "单站点长期均值趋势（按月/季/年含5dB分档）、"
                "城市/功能区/站点多对象趋势与汇总对比。"
                "输出含变化值、改善率、排名变化与趋势方向；缺测值以-99表示。"
                "站点/城市编码可先用 get_jiangxi_noise_directory 查询。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "年度同比",
                        "type": "object",
                        "properties": {
                            "trend": {"const": "year_on_year"},
                            "base_year": {
                                "type": "integer",
                                "description": "基准年份，例如 2025",
                            },
                            "compare_years": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 2,
                                "items": {"type": "integer"},
                                "description": "恰好两个对比年份，不能包含基准年",
                            },
                            "dimension": dimension_prop,
                            "indicator": indicator_prop,
                            "city_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "城市编码列表（城市维度），留空查全部城市",
                            },
                            "station_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "站点编码列表（站点维度），留空查全部功能区站点",
                            },
                        },
                        "required": [
                            "trend",
                            "base_year",
                            "compare_years",
                            "dimension",
                            "indicator",
                        ],
                        "additionalProperties": False,
                    },
                    {
                        "title": "月度/季度环比",
                        "type": "object",
                        "properties": {
                            "trend": {"const": "period_on_period"},
                            "period": {
                                "type": "string",
                                "enum": ["month", "quarter"],
                                "description": "环比周期：month=月度、quarter=季度",
                            },
                            "time_point": {
                                "type": "string",
                                "description": (
                                    "目标周期内任意时刻，例如 2026-09-15T00:00:00+08:00，"
                                    "服务端按所在月/季度计算"
                                ),
                            },
                            "dimension": dimension_prop,
                            "indicator": indicator_prop,
                            "city_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "城市编码列表（城市维度），留空查全部",
                            },
                            "station_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "站点编码列表（站点维度），留空查全部",
                            },
                        },
                        "required": [
                            "trend",
                            "period",
                            "time_point",
                            "dimension",
                            "indicator",
                        ],
                        "additionalProperties": False,
                    },
                    {
                        "title": "24小时趋势",
                        "description": "单站点监测日与对比日的24小时曲线（07:00至次日06:00）与超标统计",
                        "type": "object",
                        "properties": {
                            "trend": {"const": "trend_24h"},
                            "station_code": {
                                "type": "string",
                                "description": "站点编码（一次只分析一个站点）",
                            },
                            "monitor_date": {
                                "type": "string",
                                "description": "监测日期，例如 2026-10-20T00:00:00+08:00",
                            },
                            "compare_date": {
                                "type": "string",
                                "description": "对比日期（可选）",
                            },
                            "review_status": data_type_prop,
                        },
                        "required": ["trend", "station_code", "monitor_date"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "长期均值趋势",
                        "description": "单站点按月/季/年的昼夜均值趋势与5dB分档统计，最长3年",
                        "type": "object",
                        "properties": {
                            "trend": {"const": "long_term_trend"},
                            "station_code": {
                                "type": "string",
                                "description": "站点编码（一次只统计一个站点）",
                            },
                            "time_scale": {
                                "type": "string",
                                "enum": ["month", "quarter", "year"],
                                "description": "统计时间尺度",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "开始时间（自动对齐周期起点）",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "结束时间（自动对齐周期终点）",
                            },
                            "review_status": data_type_prop,
                        },
                        "required": [
                            "trend",
                            "station_code",
                            "time_scale",
                            "start_time",
                            "end_time",
                        ],
                        "additionalProperties": False,
                    },
                    {
                        "title": "多对象对比",
                        "description": "城市/功能区/站点之间的趋势曲线与范围汇总对比",
                        "type": "object",
                        "properties": {
                            "trend": {"const": "compare"},
                            "dimension": {
                                "type": "string",
                                "enum": ["city", "function_area", "station"],
                                "description": "对比维度：city=城市、function_area=功能区类别、station=站点",
                            },
                            "granularity": {
                                "type": "string",
                                "enum": ["hour", "day", "month", "year"],
                                "description": "统计粒度；hour 建议范围不超过7天",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "开始时间，最长370天",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "结束时间",
                            },
                            "city_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "城市编码列表（城市/功能区维度）",
                            },
                            "station_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "站点编码列表（站点维度）",
                            },
                        },
                        "required": ["trend", "dimension", "granularity", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_trends",
            description="查询江西省噪声趋势对比分析（同比/环比/24小时/长期趋势/多对象对比）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )
        self._client = client

    def _get_client(self) -> JiangxiNoiseDataClient:
        if self._client is None:
            self._client = JiangxiNoiseDataClient.from_env()
        return self._client

    def _codes_for_dimension(
        self, args: dict[str, Any], dimension: str
    ) -> tuple[list[str], list[str]]:
        if dimension == "city":
            city_codes = optional_code_list(args.get("city_codes"), "city_codes")
            return city_codes, []
        station_codes = optional_code_list(args.get("station_codes"), "station_codes")
        return [], station_codes

    async def _execute_year_on_year(self, args: dict[str, Any]) -> dict[str, Any]:
        base_year = args.get("base_year")
        compare_years = args.get("compare_years")
        if isinstance(base_year, bool) or not isinstance(base_year, int) or base_year <= 0:
            raise ToolInputError("invalid_base_year", "base_year 必须是正整数年份")
        if (
            not isinstance(compare_years, list)
            or len(compare_years) != 2
            or any(isinstance(y, bool) or not isinstance(y, int) or y <= 0 for y in compare_years)
        ):
            raise ToolInputError(
                "invalid_compare_years", "compare_years 必须是恰好两个年份"
            )
        unique_years = sorted(set(compare_years))
        if base_year in unique_years or len(unique_years) != 2:
            raise ToolInputError(
                "invalid_compare_years",
                "compare_years 不能包含基准年且两个年份不能相同",
            )
        dimension = require_enum(args.get("dimension"), YOY_DIMENSION, "dimension")
        indicator = require_enum(args.get("indicator"), YOY_INDICATOR, "indicator")
        city_codes, station_codes = self._codes_for_dimension(args, args.get("dimension"))
        body = {
            "baseYear": base_year,
            "compareYears": unique_years,
            "dimension": dimension,
            "indicator": indicator,
            "cityCodes": city_codes,
            "stationCodes": station_codes,
        }
        result = await self._get_client().query_platform_api(
            "year_on_year", json_body=body
        )
        return {"success": True, "data": result.get("data"), "trend": "year_on_year"}

    async def _execute_period_on_period(self, args: dict[str, Any]) -> dict[str, Any]:
        period = require_enum(args.get("period"), PERIOD_TYPE, "period")
        time_point = parse_datetime_param(args.get("time_point"), "time_point")
        dimension_value = require_enum(args.get("dimension"), YOY_DIMENSION, "dimension")
        indicator = require_enum(args.get("indicator"), YOY_INDICATOR, "indicator")
        city_codes, station_codes = self._codes_for_dimension(args, args.get("dimension"))
        body = {
            "period": period,
            "timePoint": platform_time(time_point),
            "dimension": dimension_value,
            "indicator": indicator,
            "cityCodes": city_codes,
            "stationCodes": station_codes,
        }
        result = await self._get_client().query_platform_api(
            "period_on_period", json_body=body
        )
        return {"success": True, "data": result.get("data"), "trend": "period_on_period"}

    async def _execute_trend_24h(self, args: dict[str, Any]) -> dict[str, Any]:
        station_code = require_code_list([args.get("station_code")], "station_code", max_count=1)
        monitor_date = parse_datetime_param(args.get("monitor_date"), "monitor_date")
        compare_date = None
        if args.get("compare_date"):
            compare_date = parse_datetime_param(args.get("compare_date"), "compare_date")
        data_type = require_enum(
            args.get("review_status", "raw"), REVIEW_STATUS_DATA_TYPE, "review_status"
        )
        body: dict[str, Any] = {
            "stationCode": station_code[0],
            "monitorDate": platform_time(monitor_date),
            "dataType": data_type,
        }
        if compare_date is not None:
            body["compareDate"] = platform_time(compare_date)
        result = await self._get_client().query_platform_api("trend_24h", json_body=body)
        return {"success": True, "data": result.get("data"), "trend": "trend_24h"}

    async def _execute_long_term_trend(self, args: dict[str, Any]) -> dict[str, Any]:
        station_code = require_code_list([args.get("station_code")], "station_code", max_count=1)
        time_scale = require_enum(args.get("time_scale"), LONG_TERM_SCALE, "time_scale")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=LONG_TERM_RANGE
        )
        data_type = require_enum(
            args.get("review_status", "raw"), REVIEW_STATUS_DATA_TYPE, "review_status"
        )
        body = {
            "stationCode": station_code[0],
            "timeScale": time_scale,
            "startTime": platform_time(start),
            "endTime": platform_time(end),
            "dataType": data_type,
        }
        result = await self._get_client().query_platform_api(
            "long_term_trend", json_body=body
        )
        return {"success": True, "data": result.get("data"), "trend": "long_term_trend"}

    async def _execute_compare(self, args: dict[str, Any]) -> dict[str, Any]:
        dimension_value = require_enum(args.get("dimension"), COMPARE_DIMENSION, "dimension")
        granularity = require_enum(args.get("granularity"), COMPARE_GRANULARITY, "granularity")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=COMPARE_RANGE
        )
        city_codes, station_codes = self._codes_for_dimension(args, args.get("dimension"))
        if dimension_value == COMPARE_DIMENSION["station"] and not station_codes:
            raise ToolInputError(
                "missing_station_codes", "站点对比必须提供 station_codes"
            )
        if dimension_value in (
            COMPARE_DIMENSION["city"],
            COMPARE_DIMENSION["function_area"],
        ) and not city_codes:
            raise ToolInputError("missing_city_codes", "城市/功能区对比必须提供 city_codes")
        body = {
            "compareDimension": dimension_value,
            "timeGranularity": granularity,
            "startTime": platform_time(start),
            "endTime": platform_time(end),
            "cityCodes": city_codes,
            "stationCodes": station_codes,
        }
        result = await self._get_client().query_platform_api(
            "noise_compare", json_body=body
        )
        return {"success": True, "data": result.get("data"), "trend": "compare"}

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            trend = kwargs.get("trend")
            handlers = {
                "year_on_year": self._execute_year_on_year,
                "period_on_period": self._execute_period_on_period,
                "trend_24h": self._execute_trend_24h,
                "long_term_trend": self._execute_long_term_trend,
                "compare": self._execute_compare,
            }
            handler = handlers.get(trend)
            if handler is None:
                raise ToolInputError(
                    "invalid_trend", "trend 必须是：" + "、".join(handlers.keys())
                )
            response = await handler(kwargs)
            logger.info("jiangxi_noise_trends_success", trend=trend)
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_trends_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
