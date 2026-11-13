"""江西省噪声超标事件分析 LLM 查询工具。

对接平台 APP 数据查询域 GetAlarmAnalysisAsync：按角色可见站点统计超限报警，
输出超标总数、处理状态、级别分布、区域/站点排名与超标事件明细。
时间口径由平台固定（today/lastDay/7day/month），无任意时段模式。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JIANGXI_CITY_CODES,
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    STATION_CODE_PATTERN_STR,
    ToolInputError,
    require_enum,
    tool_error_response,
    validate_max_results,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# GetAlarmAnalysisInput.TimeType：平台默认 today，其余值非法时按 today 处理
ALARM_TIME_TYPE = {"today": "today", "lastDay": "lastDay", "7day": "7day", "month": "month"}

PROVINCE_CODE = "360000"

CITY_CODE_PATTERN = re.compile(r"^\d{6}$")

TIME_TYPE_NOTES = "today=今日、lastDay=昨日、7day=近7天（含今日）、month=本月"


def resolve_city_or_province(value: Any) -> str:
    """解析城市名称/6位城市编码/省编码，返回平台 CityCode 参数。"""
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError("invalid_city", "city 必须是城市名称或6位编码")
    text = value.strip()
    if text in ("江西省", PROVINCE_CODE):
        return PROVINCE_CODE
    code = JIANGXI_CITY_CODES.get(text)
    if code:
        return code
    if CITY_CODE_PATTERN.fullmatch(text):
        return text
    raise ToolInputError("invalid_city", f"不支持的城市：{text}（可用名称或6位编码）")


class GetJiangxiNoiseAlarmAnalysisTool(LLMTool):
    """查询江西省噪声超标事件统计分析。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "get_jiangxi_noise_alarm_analysis",
            "description": (
                "查询江西省噪声超标（超限报警）事件统计分析：超标总数、未处理/已处理数、"
                "涉及站点数、级别分布（轻微/中度/严重）、区域超标排名（城市或区县口径）、"
                "站点超标排名与超标事件明细（限值/实测值/超标量/处理状态）。"
                f"时间口径固定为{TIME_TYPE_NOTES}，不支持任意时段；"
                "城市可用名称（如南昌市）或6位编码，360000=全省；"
                "区县编码可用 get_jiangxi_noise_directory 查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "time_type": {
                        "type": "string",
                        "enum": list(ALARM_TIME_TYPE),
                        "default": "today",
                        "description": f"统计时段。{TIME_TYPE_NOTES}",
                    },
                    "city": {
                        "type": "string",
                        "description": "城市名称或6位编码，360000=全省汇总；留空=全省",
                    },
                    "district_code": {
                        "type": "string",
                        "description": "区县编码（提供后按区县口径排名并过滤该区县）",
                    },
                    "max_records": {
                        "type": "integer",
                        "default": 20,
                        "description": "事件明细最多返回条数（汇总与排名不受影响）",
                    },
                },
                "additionalProperties": False,
            },
        }
        super().__init__(
            name="get_jiangxi_noise_alarm_analysis",
            description="查询江西省噪声超标事件统计分析（总数/级别分布/区域与站点排名/事件明细）",
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

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            time_type = require_enum(
                kwargs.get("time_type") or "today", ALARM_TIME_TYPE, "time_type"
            )
            limit = validate_max_results(kwargs.get("max_records", 20))

            params: dict[str, str] = {"TimeType": time_type}
            city = kwargs.get("city")
            if city is not None and str(city).strip():
                params["CityCode"] = resolve_city_or_province(city)
            district_code = kwargs.get("district_code")
            if district_code is not None and str(district_code).strip():
                code = str(district_code).strip()
                if not re.fullmatch(STATION_CODE_PATTERN_STR, code):
                    raise ToolInputError("invalid_district_code", f"无效区县编码：{code}")
                params["DistrictCode"] = code

            result = await self._get_client().query_platform_api(
                "alarm_analysis", params=params
            )
            data = result.get("data")
            if not isinstance(data, dict):
                raise JiangxiNoiseClientError(
                    "invalid_response", "超标事件分析返回格式不正确"
                )

            records = data.get("alarmRecords")
            total_records = len(records) if isinstance(records, list) else 0
            response: dict[str, Any] = {
                "success": True,
                "data": data,
                "record_total": total_records,
                "time_type": time_type,
            }
            if "CityCode" in params:
                response["city_code"] = params["CityCode"]
            if "DistrictCode" in params:
                response["district_code"] = params["DistrictCode"]
            if isinstance(records, list) and total_records > limit:
                data["alarmRecords"] = records[:limit]
                response["record_count"] = limit
                response["truncated"] = True
                response["hint"] = (
                    f"事件明细已截断（共 {total_records} 条，返回前 {limit} 条），"
                    "汇总与排名数据完整；如需更多明细请缩小时间或区域范围"
                )
            else:
                response["record_count"] = total_records
                response["truncated"] = False
            logger.info(
                "jiangxi_noise_alarm_analysis_success",
                time_type=time_type,
                record_total=total_records,
            )
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_alarm_analysis_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
