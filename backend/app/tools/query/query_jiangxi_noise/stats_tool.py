"""江西省噪声统计评价考核 LLM 查询工具。

覆盖平台统计评价域：站点/区域任意周期统计、声环境质量评价概览与明细、
功能区评价与达标率、区域（网格）年度评价、区县月达标率排名、区域声级排名。
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    EVALUATE_TIME_TYPE,
    REGION_TYPE,
    REVIEW_STATUS_DATA_TYPE,
    ToolInputError,
    array_query_params,
    list_response,
    object_response,
    optional_code_list,
    parse_time_range,
    platform_time,
    require_code_list,
    require_enum,
    tool_error_response,
    validate_max_results,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

STATS_RANGE = timedelta(days=400)

PERIOD_NOTE = "period 取值：day=日、month=月、quarter=季、year=年、any_range=任意时段"


class GetJiangxiNoiseStatisticsTool(LLMTool):
    """查询江西省噪声统计评价考核数据。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        time_props = {
            "start_time": {
                "type": "string",
                "description": "ISO 8601 开始时间，例如 2026-01-01T00:00:00+08:00",
            },
            "end_time": {
                "type": "string",
                "description": "ISO 8601 结束时间，例如 2026-12-31T23:59:59+08:00",
            },
        }
        function_schema = {
            "name": "get_jiangxi_noise_statistics",
            "description": (
                "查询江西省噪声统计评价考核数据（官方评价口径）。"
                "支持：站点任意周期统计（按日/月/季/年/任意时段汇总达标率与Ld/Ln/Ldn/VDR）、"
                "区县/城市/省级周期统计、声环境质量评价概览与站点日评价明细、"
                "功能区（0~4类）季度/年度评价与昼夜达标率、区域网格噪声年度评价、"
                "区县月达标率排名、区域昼夜声级与达标率排名。"
                "达标口径：昼间Ld为06:00-22:00、夜间Ln为22:00-06:00，按GB3096功能区限值判定；"
                "缺测值以-99表示。区县/城市编码可用 get_jiangxi_noise_directory 查询。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "站点周期统计",
                        "description": "按站点统计月/季/年/任意时段的达标点次、达标率、Ld/Ln/Ldn/VDR",
                        "type": "object",
                        "properties": {
                            "report": {"const": "station_period_stats"},
                            **time_props,
                            "period": {
                                "type": "string",
                                "enum": ["day", "month", "quarter", "year", "any_range"],
                                "description": f"统计周期类型。{PERIOD_NOTE}；"
                                "day/month/quarter/year 按周期逐段输出，any_range 合并输出",
                            },
                            "station_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "站点编码列表",
                            },
                            "review_status": {
                                "type": "string",
                                "enum": ["raw", "audited"],
                                "default": "audited",
                                "description": "raw=原始数据，audited=审核数据（评价建议用审核数据）",
                            },
                        },
                        "required": ["report", "period", "station_codes", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "区域周期统计",
                        "description": "按区县/城市/省统计日/月/季/年/任意时段的评价数据",
                        "type": "object",
                        "properties": {
                            "report": {"const": "region_period_stats"},
                            **time_props,
                            "period": {
                                "type": "string",
                                "enum": ["day", "month", "quarter", "year", "any_range"],
                                "description": PERIOD_NOTE,
                            },
                            "region_type": {
                                "type": "string",
                                "enum": ["district", "city", "province"],
                                "description": "区域维度：district=区县、city=城市、province=省份汇总",
                            },
                            "codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "区域编码列表：区县维度传区县编码、城市维度传城市编码，"
                                    "留空查询全部"
                                ),
                            },
                            "review_status": {
                                "type": "string",
                                "enum": ["raw", "audited"],
                                "default": "audited",
                                "description": "raw=原始数据，audited=审核数据",
                            },
                        },
                        "required": ["report", "period", "region_type", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "声环境质量评价概览",
                        "description": "站点数量、覆盖区县、昼/夜间达标点数与达标率、综合达标率（昼60%夜40%加权）",
                        "type": "object",
                        "properties": {
                            "report": {"const": "quality_summary"},
                            **time_props,
                            "station_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "站点编码列表，留空查询全部功能区站点",
                            },
                        },
                        "required": ["report", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "站点日评价明细",
                        "description": "逐站点逐日的Ld/Ln与限值、是否达标、评价结果明细表",
                        "type": "object",
                        "properties": {
                            "report": {"const": "quality_detail"},
                            **time_props,
                            "station_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "站点编码列表，留空查询全部功能区站点",
                            },
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                                "description": "最多返回记录数",
                            },
                        },
                        "required": ["report", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "功能区评价",
                        "description": "按季度或年度统计各功能区（0/1/2/3/4a/4b类）的监测点次、达标点次、达标率与Ld/Ln",
                        "type": "object",
                        "properties": {
                            "report": {"const": "fun_evaluation"},
                            **time_props,
                            "period": {
                                "type": "string",
                                "enum": ["quarter", "year"],
                                "description": "统计口径：quarter=按季度、year=按年度（时间自动对齐季度/年度边界）",
                            },
                            "area_type": {
                                "type": "string",
                                "enum": ["city", "district"],
                                "description": "codes 的类型：city=城市编码、district=区县编码，留空查全部",
                            },
                            "codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "区域编码列表（与 area_type 对应）",
                            },
                        },
                        "required": ["report", "period", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "功能区昼夜达标率",
                        "description": "所选区域功能区按1/2/3/4类分昼间的Ld、Ln及达标率",
                        "type": "object",
                        "properties": {
                            "report": {"const": "fun_attainment_rate"},
                            **time_props,
                            "day_night": {
                                "type": "string",
                                "enum": ["day", "night"],
                                "description": "day=昼间、night=夜间",
                            },
                            "area_type": {
                                "type": "string",
                                "enum": ["city", "district"],
                                "description": "codes 的类型：city=城市编码、district=区县编码，留空查全部",
                            },
                            "codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "区域编码列表（与 area_type 对应）",
                            },
                        },
                        "required": ["report", "day_night", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "区域网格噪声年度评价",
                        "description": "区域（网格）噪声年度评价：平均等效声级、评价等级、声源结构（手工监测口径）",
                        "type": "object",
                        "properties": {
                            "report": {"const": "area_evaluation"},
                            "year_start": {
                                "type": "string",
                                "description": "起始年份，例如 2025-01-01T00:00:00+08:00（按年对齐）",
                            },
                            "year_end": {
                                "type": "string",
                                "description": "结束年份，例如 2025-12-31T00:00:00+08:00（按年对齐）",
                            },
                            "day_night": {
                                "type": "string",
                                "enum": ["day", "night"],
                                "description": "day=昼间、night=夜间",
                            },
                            "city_type": {
                                "type": "string",
                                "enum": ["district", "city", "province"],
                                "description": "统计方式：district=按区县、city=按城市、province=按省份",
                            },
                            "codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "区县编码列表，留空查全部",
                            },
                        },
                        "required": ["report", "year_start", "year_end", "day_night", "city_type"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "区县月达标率排名",
                        "description": "指定月份各区县的Ld/Ln/Ldn、VDR与昼/夜达标率排名",
                        "type": "object",
                        "properties": {
                            "report": {"const": "district_month_rate"},
                            "month_time": {
                                "type": "string",
                                "description": "目标月份内任意时刻，例如 2026-09-15T00:00:00+08:00",
                            },
                            "district_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "区县编码列表，留空查全部区县",
                            },
                            "review_status": {
                                "type": "string",
                                "enum": ["raw", "audited"],
                                "default": "audited",
                                "description": "raw=原始数据，audited=审核数据",
                            },
                        },
                        "required": ["report", "month_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "区域声级与达标率排名",
                        "description": "首页口径：各区域Ld/Ln/Ldn、采集率、昼/夜达标率及排名（昨日/当月/累计）",
                        "type": "object",
                        "properties": {
                            "report": {"const": "region_noise_ranking"},
                            "period": {
                                "type": "string",
                                "enum": ["yesterday", "month", "accumulate"],
                                "description": (
                                    "yesterday=昨日（time_point 当日）、"
                                    "month=当月（time_point 所在月）、"
                                    "accumulate=累计（start_time 至 end_time）"
                                ),
                            },
                            "time_point": {
                                "type": "string",
                                "description": "yesterday/month 模式的目标时刻，例如 2026-10-22T00:00:00+08:00",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "accumulate 模式的开始时间",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "accumulate 模式的结束时间",
                            },
                            "city_code": {
                                "type": "string",
                                "description": "6位城市编码，留空查全省",
                            },
                        },
                        "required": ["report", "period"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_statistics",
            description="查询江西省噪声统计评价考核数据（周期统计/达标率/功能区与区域评价/排名）",
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

    async def _execute_station_period_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        period = require_enum(args.get("period"), EVALUATE_TIME_TYPE, "period")
        codes = require_code_list(args.get("station_codes"), "station_codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=STATS_RANGE
        )
        review_status = args.get("review_status", "audited")
        data_type = require_enum(review_status, REVIEW_STATUS_DATA_TYPE, "review_status")
        body = {
            "regionType": 0,
            "includeProvince": False,
            "timeType": period,
            "dataType": data_type,
            "timePoint": [platform_time(start), platform_time(end)],
            "codes": codes,
        }
        result = await self._get_client().query_platform_api(
            "station_period_stats", json_body=body
        )
        return list_response(
            variant="station_period_stats",
            result=result,
            limit=1000,
            extra={"period": args.get("period"), "start_time": start.isoformat(),
                   "end_time": end.isoformat()},
        )

    async def _execute_region_period_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        period = require_enum(args.get("period"), EVALUATE_TIME_TYPE, "period")
        region_type = require_enum(args.get("region_type"), REGION_TYPE, "region_type")
        codes = optional_code_list(args.get("codes"), "codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=STATS_RANGE
        )
        review_status = args.get("review_status", "audited")
        data_type = require_enum(review_status, REVIEW_STATUS_DATA_TYPE, "review_status")
        body = {
            "regionType": region_type,
            "includeProvince": False,
            "timeType": period,
            "dataType": data_type,
            "timePoint": [platform_time(start), platform_time(end)],
            "codes": codes,
        }
        result = await self._get_client().query_platform_api(
            "region_period_stats", json_body=body
        )
        return list_response(
            variant="region_period_stats",
            result=result,
            limit=1000,
            extra={"period": args.get("period"), "region_type": args.get("region_type"),
                   "start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_quality(self, args: dict[str, Any], variant: str) -> dict[str, Any]:
        codes = optional_code_list(args.get("station_codes"), "station_codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=STATS_RANGE
        )
        body: dict[str, Any] = {
            "startTime": platform_time(start),
            "endTime": platform_time(end),
            "stationCodes": codes,
        }
        limit = 50
        if variant == "quality_detail":
            limit = validate_max_results(args.get("max_results", 50))
            body["skipCount"] = 0
            body["maxResultCount"] = limit
        result = await self._get_client().query_platform_api(variant, json_body=body)
        extra = {"start_time": start.isoformat(), "end_time": end.isoformat()}
        if variant == "quality_detail":
            return list_response(
                variant=variant, result=result, limit=limit, extra=extra
            )
        return object_response(variant=variant, result=result, extra=extra)

    async def _execute_fun(self, args: dict[str, Any], variant: str) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if variant == "fun_evaluation":
            period = require_enum(args.get("period"), {"quarter": 5, "year": 7}, "period")
        else:
            period = 7
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=STATS_RANGE
        )
        area_type_value = 0
        if args.get("area_type") is not None:
            area_type_value = require_enum(
                args.get("area_type"), {"city": 1, "district": 2}, "area_type"
            )
        codes = optional_code_list(args.get("codes"), "codes")
        body.update(
            {
                "startTime": platform_time(start),
                "endTime": platform_time(end),
                "timeType": period,
                "areaType": area_type_value,
                "codes": codes,
                "stationType": 0,
                "skipCount": 0,
                "maxResultCount": 1000,
            }
        )
        if variant == "fun_attainment_rate":
            day_night = require_enum(args.get("day_night"), {"day": 1, "night": 0}, "day_night")
            body["isDay"] = day_night
        result = await self._get_client().query_platform_api(variant, json_body=body)
        return list_response(
            variant=variant, result=result, limit=1000,
            extra={"start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_area_evaluation(self, args: dict[str, Any]) -> dict[str, Any]:
        year_start = parse_time_range(
            args.get("year_start"), args.get("year_end"), max_span=timedelta(days=1900)
        )
        day_night = require_enum(args.get("day_night"), {"day": 1, "night": 0}, "day_night")
        city_type = require_enum(
            args.get("city_type"), {"district": 0, "city": 1, "province": 2}, "city_type"
        )
        codes = optional_code_list(args.get("codes"), "codes")
        body = {
            "yearStart": platform_time(year_start[0]),
            "yearEnd": platform_time(year_start[1]),
            "isDay": day_night,
            "cityType": city_type,
            "codes": codes,
            "stationType": 0,
            "timeType": 7,
            "skipCount": 0,
            "maxResultCount": 1000,
        }
        result = await self._get_client().query_platform_api(
            "area_evaluation", json_body=body
        )
        return list_response(
            variant="area_evaluation", result=result, limit=1000,
            extra={"year_start": year_start[0].isoformat(),
                   "year_end": year_start[1].isoformat()},
        )

    async def _execute_district_month_rate(self, args: dict[str, Any]) -> dict[str, Any]:
        month_time = parse_datetime_single(args.get("month_time"), "month_time")
        codes = optional_code_list(args.get("district_codes"), "district_codes")
        review_status = args.get("review_status", "audited")
        data_type = require_enum(review_status, REVIEW_STATUS_DATA_TYPE, "review_status")
        params: dict[str, Any] = {
            "dataType": data_type,
            "timePoint[0]": platform_time(month_time),
        }
        params.update(array_query_params("areaCodes", codes))
        result = await self._get_client().query_platform_api(
            "district_month_rate", params=params
        )
        return list_response(
            variant="district_month_rate", result=result, limit=1000,
            extra={"month_time": month_time.isoformat()},
        )

    async def _execute_region_ranking(self, args: dict[str, Any]) -> dict[str, Any]:
        period = args.get("period")
        if period not in {"yesterday", "month", "accumulate"}:
            raise ToolInputError(
                "invalid_period", "period 必须是 yesterday、month 或 accumulate"
            )
        params: dict[str, Any] = {}
        if period == "accumulate":
            start, end = parse_time_range(
                args.get("start_time"), args.get("end_time"), max_span=STATS_RANGE
            )
            params["timeType"] = "累计"
            params["timePoint[0]"] = platform_time(start)
            params["timePoint[1]"] = platform_time(end)
            extra = {"period": period, "start_time": start.isoformat(),
                     "end_time": end.isoformat()}
        else:
            time_point = parse_datetime_single(
                args.get("time_point"), "time_point（yesterday/month 模式必填）"
            )
            params["timeType"] = "昨日" if period == "yesterday" else "month"
            params["timePoint[0]"] = platform_time(time_point)
            extra = {"period": period, "time_point": time_point.isoformat()}
        city_code = args.get("city_code")
        if city_code is not None:
            if not isinstance(city_code, str) or not city_code.strip():
                raise ToolInputError("invalid_city_code", "city_code 必须是6位城市编码")
            params["cityCode"] = city_code.strip()
        result = await self._get_client().query_platform_api(
            "region_noise_ranking", params=params
        )
        return object_response(variant="region_noise_ranking", result=result, extra=extra)

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            report = kwargs.get("report")
            handlers = {
                "station_period_stats": self._execute_station_period_stats,
                "region_period_stats": self._execute_region_period_stats,
                "quality_summary": lambda a: self._execute_quality(a, "quality_summary"),
                "quality_detail": lambda a: self._execute_quality(a, "quality_detail"),
                "fun_evaluation": lambda a: self._execute_fun(a, "fun_evaluation"),
                "fun_attainment_rate": lambda a: self._execute_fun(a, "fun_attainment_rate"),
                "area_evaluation": self._execute_area_evaluation,
                "district_month_rate": self._execute_district_month_rate,
                "region_noise_ranking": self._execute_region_ranking,
            }
            handler = handlers.get(report)
            if handler is None:
                raise ToolInputError(
                    "invalid_report",
                    "report 必须是：" + "、".join(handlers.keys()),
                )
            response = await handler(kwargs)
            logger.info(
                "jiangxi_noise_stats_success",
                report=report,
                count=response.get("count", "object"),
            )
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_stats_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)


def parse_datetime_single(value: Any, field_name: str):
    from app.tools.query.query_jiangxi_noise.common import parse_datetime_param

    return parse_datetime_param(value, field_name)
