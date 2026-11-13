"""江西省噪声达标统计 LLM 查询工具。

对接平台数据分析域 NoiseComplianceStatistics：
- GetStatisticsAsync：城市/功能区/站点三级昼夜达标率统计（须恰好构成一个统计周期）。
- GetComparisonAsync：剔除异常气象数据前后的达标天数对比（任意日期范围，分页）。

周期口径与平台 NoiseEvaluateHelper.CreatePeriods 对齐：day=同一天、month=同一自然月、
quarter=同一季度、year=同一自然年；工具按 period_date 所在周期展开起止日期。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
    resolve_city_codes,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    REVIEW_STATUS_DATA_TYPE,
    ToolInputError,
    from_client_error,
    list_response,
    parse_datetime_param,
    platform_time,
    require_code_list,
    require_enum,
    tool_error_response,
    validate_max_results,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# GetNoiseComplianceStatisticsInput.TimeType（平台 TimeType 枚举，须构成恰好一个周期）
COMPLIANCE_PERIOD = {"day": 30, "month": 40, "quarter": 45, "year": 55}

COMPARISON_MAX_SPAN = timedelta(days=366)

PERIOD_NOTES = "day=日、month=月、quarter=季、year=年"


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def resolve_period_range(period: str, period_date: datetime) -> tuple[datetime, datetime, str]:
    """将周期类型与周期内任意一天展开为该自然周期的起止日期（上海本地时间）。

    返回 (start, end, label)：start 为周期首日 00:00，end 为周期最后一日 00:00
    （平台 CreatePeriods 按 EndDate.Date 闭区间覆盖，起止必须落在同一周期内）。
    """
    value = period_date
    if period == "day":
        start = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start, start.strftime("%Y-%m-%d")
    if period == "month":
        start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, _add_months(start, 1).replace(day=1) - timedelta(days=1), start.strftime("%Y-%m")
    if period == "quarter":
        quarter_start_month = (value.month - 1) // 3 * 3 + 1
        start = value.replace(
            month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end = _add_months(start, 3).replace(day=1) - timedelta(days=1)
        return start, end, f"{start.year}Q{(quarter_start_month - 1) // 3 + 1}"
    if period == "year":
        start = value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1) - timedelta(days=1)
        return start, end, str(start.year)
    raise ToolInputError("invalid_period", f"period 必须是：{PERIOD_NOTES}")


def _resolve_cities(values: Any) -> list[str]:
    if isinstance(values, str):  # 容错：LLM 可能把单城市传成字符串
        values = [values]
    try:
        return resolve_city_codes([str(item).strip() for item in values or []])
    except JiangxiNoiseClientError as exc:  # resolve_city_codes 的城市名/编码校验
        raise from_client_error(exc)


class GetJiangxiNoiseComplianceTool(LLMTool):
    """查询江西省噪声达标统计与气象剔除对比。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "get_jiangxi_noise_compliance",
            "description": (
                "查询江西省噪声达标统计（GB3096 功能区限值口径）："
                "statistics=按月/季/年等周期输出城市/功能区/站点三级昼夜达标率、"
                "达标天数、超标次数与监测天数汇总；"
                "comparison=对比剔除异常气象数据前后的昼/夜达标天数变化"
                "（支持城市或区县范围、任意日期范围、分页）。"
                "城市可用名称或6位编码，区县编码可用 get_jiangxi_noise_directory 查询；"
                "raw=原始数据，audited=审核数据（评价建议用审核数据）。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "达标统计",
                        "description": "单个自然周期（日/月/季/年）的城市/功能区/站点达标率统计",
                        "type": "object",
                        "properties": {
                            "report": {"const": "statistics"},
                            "city_names": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                                "description": "城市名称或6位编码列表（必填）",
                            },
                            "period": {
                                "type": "string",
                                "enum": list(COMPLIANCE_PERIOD),
                                "description": f"统计周期类型。{PERIOD_NOTES}",
                            },
                            "period_date": {
                                "type": "string",
                                "description": (
                                    "目标周期内任意日期（ISO 8601），"
                                    "例如 2026-07-15T00:00:00+08:00 表示 7 月/三季度/2026 年"
                                ),
                            },
                            "review_status": {
                                "type": "string",
                                "enum": ["raw", "audited"],
                                "default": "audited",
                                "description": "raw=原始数据，audited=审核数据",
                            },
                            "max_records": {
                                "type": "integer",
                                "default": 50,
                                "description": "站点级明细最多返回条数（汇总/城市/功能区完整返回）",
                            },
                        },
                        "required": ["report", "city_names", "period", "period_date"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "气象剔除达标对比",
                        "description": "任意日期范围内，剔除异常气象数据前后的昼/夜达标天数对比",
                        "type": "object",
                        "properties": {
                            "report": {"const": "comparison"},
                            "city_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "城市名称或6位编码列表（与 district_codes 至少提供一个）",
                            },
                            "district_codes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "区县编码列表（与 city_names 至少提供一个）",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "开始日期（ISO 8601）",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "结束日期（ISO 8601），单次不超过 366 天",
                            },
                            "review_status": {
                                "type": "string",
                                "enum": ["raw", "audited"],
                                "default": "audited",
                                "description": "raw=原始数据，audited=审核数据",
                            },
                            "max_results": {
                                "type": "integer",
                                "default": 20,
                                "description": "每页条数（1-100）",
                            },
                        },
                        "required": ["report", "start_date", "end_date"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_compliance",
            description="查询江西省噪声达标统计（三级达标率）与气象剔除达标天数对比",
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

    async def _execute_statistics(self, args: dict[str, Any]) -> dict[str, Any]:
        cities = _resolve_cities(args.get("city_names"))
        if not cities:
            raise ToolInputError(
                "missing_city_names", "statistics 模式必须提供 city_names"
            )
        period = require_enum(args.get("period"), COMPLIANCE_PERIOD, "period")
        period_date = parse_datetime_param(args.get("period_date"), "period_date")
        review_status = args.get("review_status") or "audited"
        data_type = require_enum(review_status, REVIEW_STATUS_DATA_TYPE, "review_status")
        limit = validate_max_results(args.get("max_records", 50))

        start, end, label = resolve_period_range(args.get("period"), period_date)
        body = {
            "CityCodes": cities,
            "DataType": data_type,
            "TimeType": period,
            "StartDate": platform_time(start),
            "EndDate": platform_time(end),
        }
        result = await self._get_client().query_platform_api(
            "compliance_statistics", json_body=body
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise JiangxiNoiseClientError(
                "invalid_response", "达标统计返回格式不正确"
            )
        stations = data.get("stations")
        station_total = len(stations) if isinstance(stations, list) else 0
        response: dict[str, Any] = {
            "success": True,
            "data": data,
            "period": args.get("period"),
            "period_label": label,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "review_status": review_status,
            "station_total": station_total,
        }
        if isinstance(stations, list) and station_total > limit:
            data["stations"] = stations[:limit]
            response["station_count"] = limit
            response["truncated"] = True
            response["hint"] = (
                f"站点级明细已截断（共 {station_total} 条，返回前 {limit} 条），"
                "汇总与城市/功能区数据完整；可缩小范围或提高 max_records"
            )
        else:
            response["station_count"] = station_total
            response["truncated"] = False
        return response

    async def _execute_comparison(self, args: dict[str, Any]) -> dict[str, Any]:
        cities = _resolve_cities(args.get("city_names"))
        districts = require_code_list(args.get("district_codes"), "district_codes", allow_empty=True)
        if not cities and not districts:
            raise ToolInputError(
                "missing_region",
                "comparison 模式必须提供 city_names 或 district_codes 至少一个",
            )
        start = parse_datetime_param(args.get("start_date"), "start_date")
        end = parse_datetime_param(args.get("end_date"), "end_date")
        if start > end:
            raise ToolInputError("invalid_time_range", "start_date 不能晚于 end_date")
        if end - start > COMPARISON_MAX_SPAN:
            raise ToolInputError(
                "time_range_too_large", "单次对比时间范围不能超过 366 天"
            )
        review_status = args.get("review_status") or "audited"
        data_type = require_enum(review_status, REVIEW_STATUS_DATA_TYPE, "review_status")
        limit = validate_max_results(args.get("max_results", 20))

        body = {
            "CityCodes": cities,
            "DistrictCodes": districts,
            "DataType": data_type,
            "StartDate": platform_time(start),
            "EndDate": platform_time(end),
            "SkipCount": 0,
            "MaxResultCount": limit,
        }
        result = await self._get_client().query_platform_api(
            "compliance_comparison", json_body=body
        )
        return list_response(
            variant="comparison",
            result=result,
            limit=limit,
            extra={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "review_status": review_status,
            },
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
                "statistics": self._execute_statistics,
                "comparison": self._execute_comparison,
            }
            handler = handlers.get(report)
            if handler is None:
                raise ToolInputError(
                    "invalid_report", "report 必须是：statistics、comparison"
                )
            response = await handler(kwargs)
            logger.info("jiangxi_noise_compliance_success", report=report)
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_compliance_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
