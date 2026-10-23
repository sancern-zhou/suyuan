"""江西省噪声平台运行状态 LLM 查询工具。

覆盖平台联网概况域：站点在线/离线状态、联网总览、数据获取率、报警记录。
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    NETWORK_DATA_TYPE,
    NETWORK_STATUS,
    RECEIVING_RATE_TYPE,
    ToolInputError,
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

RATE_RANGE = timedelta(days=31)


class GetJiangxiNoiseRuntimeStatusTool(LLMTool):
    """查询江西省噪声监测站点运行状态。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        status_prop = {
            "type": "string",
            "enum": ["all", "online", "offline"],
            "default": "all",
            "description": "站点状态过滤：all=全部、online=在线、offline=离线",
        }
        function_schema = {
            "name": "get_jiangxi_noise_runtime_status",
            "description": (
                "查询江西省噪声监测站点运行状态。支持：联网总览（总/在线/离线数量与"
                "离线站点最后数据时间）、逐站点在离线状态与各监测项有效性、"
                "数据获取率/有效率（Leq/L5~L95/气象项与建议检查项）、报警记录。"
                "在线判定：分钟数据15分钟内、小时数据75分钟内有有效数据。"
                "站点编码可先用 get_jiangxi_noise_directory 查询。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "联网总览",
                        "description": "指定城市的站点总数、在线数、离线数与离线站点列表",
                        "type": "object",
                        "properties": {
                            "report": {"const": "network_overview"},
                            "city_code": {
                                "type": "string",
                                "description": "6位城市编码，例如 360100（必填）",
                            },
                            "status_filter": status_prop,
                            "data_type": {
                                "type": "string",
                                "enum": ["minute", "hour"],
                                "default": "minute",
                                "description": "判定所用数据粒度：minute=分钟数据、hour=小时数据",
                            },
                        },
                        "required": ["report", "city_code"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "站点在线状态",
                        "description": "逐站点在线状态与各监测项（Leq/气象等）最近值与有效性",
                        "type": "object",
                        "properties": {
                            "report": {"const": "station_network_status"},
                            "station_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "站点编码列表",
                            },
                            "status_filter": status_prop,
                            "data_type": {
                                "type": "string",
                                "enum": ["minute", "hour"],
                                "default": "minute",
                                "description": "判定所用数据粒度",
                            },
                        },
                        "required": ["report", "station_codes"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "数据获取率",
                        "description": "按站点统计获取率或有效率（含各监测项计数与建议检查项），最长31天",
                        "type": "object",
                        "properties": {
                            "report": {"const": "data_receiving_rate"},
                            "station_codes": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "站点编码列表",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "ISO 8601 开始时间",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "ISO 8601 结束时间",
                            },
                            "rate_type": {
                                "type": "string",
                                "enum": ["receiving", "effective"],
                                "default": "receiving",
                                "description": "receiving=获取率、effective=有效率",
                            },
                        },
                        "required": ["report", "station_codes", "start_time", "end_time"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "报警记录",
                        "description": "报警通知记录（报警时间、内容、通知电话与发送状态），支持站点名称模糊查询",
                        "type": "object",
                        "properties": {
                            "report": {"const": "alarm_records"},
                            "station_name": {
                                "type": "string",
                                "description": "站点名称（模糊匹配，可选）",
                            },
                            "phone": {
                                "type": "string",
                                "description": "通知电话（精确匹配，可选）",
                            },
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                                "description": "最多返回记录数",
                            },
                        },
                        "required": ["report"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_runtime_status",
            description="查询江西省噪声站点运行状态（联网总览/在线状态/数据获取率/报警记录）",
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

    async def _execute_network_overview(self, args: dict[str, Any]) -> dict[str, Any]:
        city_code = args.get("city_code")
        if not isinstance(city_code, str) or not city_code.strip():
            raise ToolInputError("invalid_city_code", "city_code 必须是6位城市编码")
        status_filter = require_enum(
            args.get("status_filter", "all"), NETWORK_STATUS, "status_filter"
        )
        data_type = require_enum(
            args.get("data_type", "minute"), NETWORK_DATA_TYPE, "data_type"
        )
        params = {
            "cityCode": city_code.strip(),
            "stationStatus": status_filter,
            "dataType": data_type,
            "srcType": 0,
            "stationType": 0,
        }
        result = await self._get_client().query_platform_api(
            "network_overview", params=params
        )
        return object_response(
            variant="network_overview", result=result,
            extra={"city_code": city_code.strip()},
        )

    async def _execute_station_network_status(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = require_code_list(args.get("station_codes"), "station_codes")
        status_filter = require_enum(
            args.get("status_filter", "all"), NETWORK_STATUS, "status_filter"
        )
        data_type = require_enum(
            args.get("data_type", "minute"), NETWORK_DATA_TYPE, "data_type"
        )
        params = {
            "stationCode": ",".join(codes),
            "stationStatus": status_filter,
            "dataType": data_type,
            "srcType": 0,
        }
        result = await self._get_client().query_platform_api(
            "station_network_status", params=params
        )
        return list_response(
            variant="station_network_status", result=result, limit=1000,
            extra={"station_codes": codes},
        )

    async def _execute_data_receiving_rate(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = require_code_list(args.get("station_codes"), "station_codes")
        start, end = parse_time_range(
            args.get("start_time"), args.get("end_time"), max_span=RATE_RANGE
        )
        rate_type = require_enum(
            args.get("rate_type", "receiving"), RECEIVING_RATE_TYPE, "rate_type"
        )
        params = {
            "stationCode": ",".join(codes),
            "srcType": 0,
            "startTime": platform_time(start),
            "endTime": platform_time(end),
            "rateType": rate_type,
        }
        result = await self._get_client().query_platform_api(
            "data_receiving_rate", params=params
        )
        return list_response(
            variant="data_receiving_rate", result=result, limit=1000,
            extra={"rate_type": args.get("rate_type", "receiving"),
                   "start_time": start.isoformat(), "end_time": end.isoformat()},
        )

    async def _execute_alarm_records(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = validate_max_results(args.get("max_results", 50))
        params: dict[str, Any] = {
            "skipCount": 0,
            "maxResultCount": limit,
        }
        station_name = args.get("station_name")
        if station_name is not None:
            if not isinstance(station_name, str) or not station_name.strip():
                raise ToolInputError("invalid_station_name", "station_name 必须是非空字符串")
            params["stationName"] = station_name.strip()
        phone = args.get("phone")
        if phone is not None:
            if not isinstance(phone, str) or not phone.strip():
                raise ToolInputError("invalid_phone", "phone 必须是非空字符串")
            params["phone"] = phone.strip()
        result = await self._get_client().query_platform_api("alarm_records", params=params)
        return list_response(variant="alarm_records", result=result, limit=limit)

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            report = kwargs.get("report")
            handlers = {
                "network_overview": self._execute_network_overview,
                "station_network_status": self._execute_station_network_status,
                "data_receiving_rate": self._execute_data_receiving_rate,
                "alarm_records": self._execute_alarm_records,
            }
            handler = handlers.get(report)
            if handler is None:
                raise ToolInputError(
                    "invalid_report", "report 必须是：" + "、".join(handlers.keys())
                )
            response = await handler(kwargs)
            logger.info("jiangxi_noise_runtime_success", report=report)
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_runtime_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
