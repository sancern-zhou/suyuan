"""江西省噪声源与噪声事件 LLM 查询工具。

覆盖平台事件域：声源类型结构分析（交通/工业/施工/生活/自然）、
噪声事件明细、事件类型占比、每日Ld/Ln与昼夜事件数量。
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    EVENT_TIME_TYPE,
    SOURCE_DIMENSION,
    ToolInputError,
    array_query_params,
    list_response,
    object_response,
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

SOURCE_ANALYSIS_RANGE = timedelta(days=370)
EVENT_LIST_RANGE = timedelta(days=31)
EVENT_SUMMARY_RANGE = timedelta(days=92)


class GetJiangxiNoiseEventsTool(LLMTool):
    """查询江西省噪声源分析与噪声事件数据。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        codes_prop = {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
            "description": "站点编码列表，可用 get_jiangxi_noise_directory 查询",
        }
        time_props = {
            "start_time": {
                "type": "string",
                "description": "ISO 8601 开始时间，例如 2026-10-01T00:00:00+08:00",
            },
            "end_time": {
                "type": "string",
                "description": "ISO 8601 结束时间，例如 2026-10-21T00:00:00+08:00",
            },
        }
        function_schema = {
            "name": "get_jiangxi_noise_events",
            "description": (
                "查询江西省噪声源与噪声事件数据（基于事件AI声源识别）。"
                "支持：声源类型结构统计（交通/工业/施工/生活/自然五类的次数、占比与平均声级，"
                "含昼夜结构）、噪声事件明细（事件起止、声学量、声源识别结果与置信度、超标值）、"
                "事件类型占比（含风雨雷鸟蛙虫等自然因素细分）、"
                "每日Ld/Ln与昼夜事件数量趋势。"
                "缺测占比/声级以占位字符串表示。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "声源结构分析",
                        "description": "按城市/区县/站点统计各声源类型次数、占比、平均Leq（含昼夜饼图结构）",
                        "type": "object",
                        "properties": {
                            "report": {"const": "source_analysis"},
                            "dimension": {
                                "type": "string",
                                "enum": ["city", "district", "station"],
                                "description": "统计维度，决定 codes 的含义：city=城市编码、district=区县编码、station=站点编码",
                            },
                            "codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "编码列表（含义由 dimension 决定）",
                            },
                            **time_props,
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                                "description": "最多返回记录数",
                            },
                        },
                        "required": ["report", "dimension", "codes", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "噪声事件明细",
                        "description": "逐条噪声事件：起止时间、Leq/Lmax/累计百分声级、声源识别与置信度、是否超标",
                        "type": "object",
                        "properties": {
                            "report": {"const": "event_list"},
                            "station_codes": codes_prop,
                            **time_props,
                            "is_exceed": {
                                "type": "boolean",
                                "default": False,
                                "description": "true=只查超标事件",
                            },
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                                "description": "最多返回记录数",
                            },
                        },
                        "required": ["report", "station_codes", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "事件类型占比",
                        "description": "按日/月/季/年统计各事件类型次数与占比（交通/工业/施工/生活/自然现象/动物鸣叫等）",
                        "type": "object",
                        "properties": {
                            "report": {"const": "event_type_percentage"},
                            "station_codes": codes_prop,
                            **time_props,
                            "period": {
                                "type": "string",
                                "enum": ["day", "month", "quarter", "year"],
                                "description": "统计时间类型",
                            },
                            "is_exceed": {
                                "type": "boolean",
                                "default": False,
                                "description": "true=只统计超标事件",
                            },
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                                "description": "最多返回记录数",
                            },
                        },
                        "required": [
                            "report",
                            "station_codes",
                            "period",
                            "start_time",
                            "end_time",
                        ],
                        "additionalProperties": False,
                    },
                    {
                        "title": "每日声级与事件数量",
                        "description": "逐日的Ld/Ln声级与昼间(06-22时)/夜间事件数趋势（柱线图数据），最长92天",
                        "type": "object",
                        "properties": {
                            "report": {"const": "event_daily_summary"},
                            "station_codes": codes_prop,
                            **time_props,
                        },
                        "required": ["report", "station_codes", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_events",
            description="查询江西省噪声源结构与噪声事件数据（声源占比/事件明细/类型占比/昼夜事件趋势）",
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

    async def _execute_source_analysis(self, args: dict[str, Any]) -> dict[str, Any]:
        dimension = require_enum(args.get("dimension"), SOURCE_DIMENSION, "dimension")
        codes = require_code_list(args.get("codes"), "codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=SOURCE_ANALYSIS_RANGE
        )
        limit = validate_max_results(args.get("max_results", 50))
        params: dict[str, Any] = {
            "areaType": dimension,
            "skipCount": 0,
            "maxResultCount": limit,
            "timePoint[0]": platform_time(start),
            "timePoint[1]": platform_time(end),
        }
        params.update(array_query_params("codes", codes))
        result = await self._get_client().query_platform_api(
            "source_analysis", params=params
        )
        return list_response(
            variant="source_analysis", result=result, limit=limit,
            extra={"dimension": args.get("dimension"),
                   "start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_event_list(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = require_code_list(args.get("station_codes"), "station_codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=EVENT_LIST_RANGE
        )
        limit = validate_max_results(args.get("max_results", 50))
        is_exceed = bool(args.get("is_exceed", False))
        params: dict[str, Any] = {
            "skipCount": 0,
            "maxResultCount": limit,
            "isExceed": is_exceed,
            "dataTime[0]": platform_time(start),
            "dataTime[1]": platform_time(end),
        }
        params.update(array_query_params("codes", codes))
        result = await self._get_client().query_platform_api("event_list", params=params)
        return list_response(
            variant="event_list", result=result, limit=limit,
            extra={"start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_event_type_percentage(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = require_code_list(args.get("station_codes"), "station_codes")
        period = require_enum(args.get("period"), EVENT_TIME_TYPE, "period")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=SOURCE_ANALYSIS_RANGE
        )
        limit = validate_max_results(args.get("max_results", 50))
        is_exceed = bool(args.get("is_exceed", False))
        params: dict[str, Any] = {
            "skipCount": 0,
            "maxResultCount": limit,
            "timeType": period,
            "isExceed": is_exceed,
            "dataTime[0]": platform_time(start),
            "dataTime[1]": platform_time(end),
        }
        params.update(array_query_params("codes", codes))
        result = await self._get_client().query_platform_api(
            "event_type_percentage", params=params
        )
        return list_response(
            variant="event_type_percentage", result=result, limit=limit,
            extra={"period": args.get("period"),
                   "start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_event_daily_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = require_code_list(args.get("station_codes"), "station_codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=EVENT_SUMMARY_RANGE
        )
        body = {
            "codes": codes,
            "timePoint": [platform_time(start), platform_time(end)],
        }
        result = await self._get_client().query_platform_api(
            "event_daily_summary", json_body=body
        )
        return object_response(
            variant="event_daily_summary", result=result,
            extra={"start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            report = kwargs.get("report")
            handlers = {
                "source_analysis": self._execute_source_analysis,
                "event_list": self._execute_event_list,
                "event_type_percentage": self._execute_event_type_percentage,
                "event_daily_summary": self._execute_event_daily_summary,
            }
            handler = handlers.get(report)
            if handler is None:
                raise ToolInputError(
                    "invalid_report", "report 必须是：" + "、".join(handlers.keys())
                )
            response = await handler(kwargs)
            logger.info("jiangxi_noise_events_success", report=report)
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_events_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
