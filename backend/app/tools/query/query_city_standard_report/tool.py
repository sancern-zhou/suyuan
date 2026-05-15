"""
城市新旧国标统计报表接口查询工具。

直接调用广东联网统计报表接口 GetReportForRangeListFilterAsync，通过 nsType
选择新/旧国标口径，不再基于本地日报数据重算城市统计指标。
同比/环比查询直接调用 GetReportForRangeCompareListFilterAsync。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.agent.context.execution_context import ExecutionContext
from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.tools.base import LLMTool, ToolCategory
from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
from app.tools.query.report_data_package import save_report_data_package

logger = structlog.get_logger()


POLLUTANT_CODE_ALIASES = {
    "SO2": "so2",
    "NO2": "no2",
    "PM10": "pm10",
    "PM2_5": "pm2_5",
    "PM2.5": "pm2_5",
    "CO": "co",
    "O3": "o3",
    "O3_8H": "o3_8h",
    "O3-8H": "o3_8h",
    "AQI": "aqi",
}

GUANGDONG_REGIONS = {
    "珠三角": ["广州", "深圳", "珠海", "佛山", "惠州", "东莞", "中山", "江门", "肇庆"],
    "粤东": ["汕头", "汕尾", "潮州", "揭阳"],
    "粤西": ["湛江", "茂名", "阳江"],
    "粤北": ["韶关", "河源", "梅州", "清远", "云浮"],
}
GUANGDONG_REGIONS["非珠三角"] = (
    GUANGDONG_REGIONS["粤东"] + GUANGDONG_REGIONS["粤西"] + GUANGDONG_REGIONS["粤北"]
)
GUANGDONG_REGIONS["粤东西北"] = GUANGDONG_REGIONS["非珠三角"]
GUANGDONG_REGIONS["全省"] = GUANGDONG_REGIONS["珠三角"] + GUANGDONG_REGIONS["非珠三角"]
GUANGDONG_REGIONS["广东省"] = GUANGDONG_REGIONS["全省"]


def expand_region_city_names(cities: List[str]) -> List[str]:
    expanded: List[str] = []
    seen = set()
    for item in cities:
        name = str(item).strip()
        candidates = GUANGDONG_REGIONS.get(name, [name])
        for city in candidates:
            if city not in seen:
                seen.add(city)
                expanded.append(city)
    return expanded


def _normalize_datetime(value: str, *, end_of_day: bool = False) -> str:
    """Accept YYYY-MM-DD or full datetime and return API datetime string."""
    value = str(value).strip()
    if len(value) == 10:
        return f"{value} {'23:59:59' if end_of_day else '00:00:00'}"
    return value


def _extract_report_records(api_result: Any) -> List[Dict[str, Any]]:
    if isinstance(api_result, dict):
        items = api_result.get("items", [])
    elif isinstance(api_result, list):
        items = api_result
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _city_name_from_record(record: Dict[str, Any]) -> str:
    return str(
        record.get("cityName")
        or record.get("CityName")
        or record.get("districtName")
        or record.get("DistrictName")
        or record.get("stationName")
        or record.get("StationName")
        or record.get("name")
        or record.get("Name")
        or record.get("stationCode")
        or record.get("StationCode")
        or ""
    ).strip()


def _records_by_city(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for idx, record in enumerate(records):
        name = _city_name_from_record(record) or f"record_{idx + 1}"
        grouped[name] = record
    return grouped


def _normalize_pollutant_codes(pollutant_codes: Optional[List[str]]) -> Optional[List[str]]:
    if not pollutant_codes:
        return None
    normalized: List[str] = []
    for code in pollutant_codes:
        raw = str(code).strip()
        if not raw:
            continue
        normalized.append(POLLUTANT_CODE_ALIASES.get(raw.upper(), raw))
    return normalized or None


def _build_city_codes(cities: Optional[List[str]], tool_name: str) -> tuple[List[str], List[str], Optional[Dict[str, Any]]]:
    requested_cities = list(cities or [])
    expanded_cities = expand_region_city_names(requested_cities) if requested_cities else []
    city_codes: List[str] = []
    for city in expanded_cities:
        code = QueryGDSuncereDataTool.get_city_code(city)
        if code:
            city_codes.append(code)
        else:
            logger.warning("city_standard_report_city_code_not_found", tool=tool_name, city=city)

    if requested_cities and not city_codes:
        return [], expanded_cities, {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {
                "tool_name": tool_name,
                "requested_cities": requested_cities,
                "error": "No valid city codes found",
            },
            "summary": f"未找到有效城市编码：{', '.join(requested_cities)}",
        }
    return city_codes, expanded_cities, None


async def execute_query_city_standard_report(
    *,
    cities: Optional[List[str]] = None,
    start_time: str,
    end_time: str,
    ns_type: int = 2,
    time_type: int = 8,
    pollutant_codes: Optional[List[str]] = None,
    plan_type: int = 0,
    data_source: int = 1,
    sand_type: int = 1,
    revise_type: int = 0,
    skip_count: int = 0,
    max_result_count: int = 200,
    context: Optional[ExecutionContext] = None,
) -> Dict[str, Any]:
    """
    查询城市统计报表。

    ns_type: 2=新国标，1=旧国标。
    """
    if ns_type not in (1, 2):
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": "query_city_standard_report", "error": "Invalid ns_type"},
            "summary": "ns_type 参数错误：1=旧国标，2=新国标",
        }

    requested_cities = list(cities or [])
    city_codes, expanded_cities, city_error = _build_city_codes(cities, "query_city_standard_report")
    if city_error:
        return city_error

    start = _normalize_datetime(start_time)
    end = _normalize_datetime(end_time, end_of_day=True)
    effective_pollutants = _normalize_pollutant_codes(pollutant_codes)

    payload: Dict[str, Any] = {
        "skipCount": skip_count,
        "maxResultCount": max_result_count,
        "TimeType": time_type,
        "AreaType": 2,
        "TimePoint": [start, end],
        "planType": plan_type,
        "dataSource": data_source,
        "sandType": sand_type,
        "ReviseType": revise_type,
        "nsType": ns_type,
    }
    if effective_pollutants:
        payload["PollutantCode"] = effective_pollutants
    if city_codes:
        payload["StationCode"] = city_codes

    logger.info(
        "query_city_standard_report_start",
        requested_cities=requested_cities,
        cities=expanded_cities,
        city_codes=city_codes,
        ns_type=ns_type,
        time_type=time_type,
        start_time=start,
        end_time=end,
    )

    try:
        api_client = get_gd_suncere_api_client()
        response = api_client._make_request(
            "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync",
            payload,
            method="POST",
            timeout=60,
        )
        if not response.get("success"):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {
                    "tool_name": "query_city_standard_report",
                    "api_state": response.get("state"),
                    "api_msg": response.get("msg"),
                    "request_payload": payload,
                },
                "summary": f"城市统计报表接口查询失败：{response.get('msg') or '未知错误'}",
            }

        records = _extract_report_records(response.get("result"))
        standard_label = "新国标" if ns_type == 2 else "旧国标"
        metadata = {
            "schema_version": "v2.0",
            "tool_name": "query_city_standard_report",
            "standard": standard_label,
            "ns_type": ns_type,
            "cities": expanded_cities,
            "requested_cities": requested_cities,
            "city_codes": city_codes,
            "time_range": f"{start} to {end}",
            "time_type": time_type,
            "plan_type": plan_type,
            "data_source": data_source,
            "sand_type": sand_type,
            "revise_type": revise_type,
            "total_records": len(records),
            "request_payload": payload,
        }

        result: Dict[str, Any] = {
            "status": "success" if records else "empty",
            "success": True,
            "data": records[:24],
            "result": records,
            "metadata": metadata,
            "summary": (
                f"{standard_label}城市统计报表接口查询完成，"
                f"{start} 至 {end}，返回 {len(records)} 条记录"
            ),
        }

        grouped = _records_by_city(records)
        report_data_id = save_report_data_package(
            context=context,
            tool_name="query_city_standard_report",
            query={
                "cities": expanded_cities,
                "requested_cities": requested_cities,
                "start_time": start,
                "end_time": end,
                "ns_type": ns_type,
                "time_type": time_type,
                "pollutant_codes": effective_pollutants,
                "plan_type": plan_type,
                "data_source": data_source,
                "sand_type": sand_type,
                "revise_type": revise_type,
            },
            result=result,
            metadata=metadata,
            primary_view_name="cities",
            primary_name_field="city",
            primary_stats=grouped,
            extra_views={"raw": records, "result": records},
            package_kind="city_standard_report_api",
        )
        if report_data_id:
            metadata["report_data_id"] = report_data_id
            result["report_data_id"] = report_data_id
            result["summary"] += f" | 完整接口报表已保存为 report_data_id: {report_data_id}"
            result["registry_usage"] = {
                "cities": f'read_data_registry(data_id="{report_data_id}", view="cities")',
                "raw": f'read_data_registry(data_id="{report_data_id}", view="raw")',
                "result": f'read_data_registry(data_id="{report_data_id}", view="result")',
            }

        return result

    except Exception as exc:
        logger.error("query_city_standard_report_failed", error=str(exc), error_type=type(exc).__name__)
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {
                "tool_name": "query_city_standard_report",
                "error": str(exc),
                "request_payload": payload,
            },
            "summary": f"城市统计报表接口查询失败：{exc}",
        }


async def execute_query_city_standard_yoy_report(
    *,
    cities: Optional[List[str]] = None,
    time_point: List[str],
    contrast_time: List[str],
    ns_type: int = 2,
    time_type: int = 8,
    pollutant_codes: Optional[List[str]] = None,
    plan_type: int = 0,
    data_source: int = 1,
    sand_type: int = 1,
    revise_type: int = 0,
    skip_count: int = 0,
    max_result_count: int = 200,
    context: Optional[ExecutionContext] = None,
) -> Dict[str, Any]:
    """
    查询城市同比/环比统计报表。

    ns_type: 2=新国标，1=旧国标。
    """
    if ns_type not in (1, 2):
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": "query_city_standard_yoy_report", "error": "Invalid ns_type"},
            "summary": "ns_type 参数错误：1=旧国标，2=新国标",
        }
    if len(time_point) != 2 or len(contrast_time) != 2:
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": "query_city_standard_yoy_report", "error": "Invalid time ranges"},
            "summary": "time_point 和 contrast_time 都必须是两个时间组成的数组",
        }

    requested_cities = list(cities or [])
    city_codes, expanded_cities, city_error = _build_city_codes(cities, "query_city_standard_yoy_report")
    if city_error:
        return city_error

    current_range = [
        _normalize_datetime(time_point[0]),
        _normalize_datetime(time_point[1], end_of_day=True),
    ]
    comparison_range = [
        _normalize_datetime(contrast_time[0]),
        _normalize_datetime(contrast_time[1], end_of_day=True),
    ]
    effective_pollutants = _normalize_pollutant_codes(pollutant_codes)

    payload: Dict[str, Any] = {
        "skipCount": skip_count,
        "maxResultCount": max_result_count,
        "TimeType": time_type,
        "AreaType": 2,
        "TimePoint": current_range,
        "contrastTime": comparison_range,
        "planType": plan_type,
        "dataSource": data_source,
        "sandType": sand_type,
        "ReviseType": revise_type,
        "nsType": ns_type,
    }
    if effective_pollutants:
        payload["PollutantCode"] = effective_pollutants
    if city_codes:
        payload["StationCode"] = city_codes

    logger.info(
        "query_city_standard_yoy_report_start",
        requested_cities=requested_cities,
        cities=expanded_cities,
        city_codes=city_codes,
        ns_type=ns_type,
        time_type=time_type,
        time_point=current_range,
        contrast_time=comparison_range,
        pollutant_codes=effective_pollutants,
    )

    try:
        api_client = get_gd_suncere_api_client()
        response = api_client._make_request(
            "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeCompareListFilterAsync",
            payload,
            method="POST",
            timeout=60,
        )
        if not response.get("success"):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {
                    "tool_name": "query_city_standard_yoy_report",
                    "api_state": response.get("state"),
                    "api_msg": response.get("msg"),
                    "request_payload": payload,
                },
                "summary": f"城市同比统计报表接口查询失败：{response.get('msg') or '未知错误'}",
            }

        records = _extract_report_records(response.get("result"))
        standard_label = "新国标" if ns_type == 2 else "旧国标"
        metadata = {
            "schema_version": "v2.0",
            "tool_name": "query_city_standard_yoy_report",
            "standard": standard_label,
            "ns_type": ns_type,
            "cities": expanded_cities,
            "requested_cities": requested_cities,
            "city_codes": city_codes,
            "time_point": current_range,
            "contrast_time": comparison_range,
            "time_type": time_type,
            "plan_type": plan_type,
            "data_source": data_source,
            "sand_type": sand_type,
            "revise_type": revise_type,
            "pollutant_codes": effective_pollutants,
            "total_records": len(records),
            "request_payload": payload,
        }

        result: Dict[str, Any] = {
            "status": "success" if records else "empty",
            "success": True,
            "data": records[:24],
            "result": records,
            "metadata": metadata,
            "summary": (
                f"{standard_label}城市同比统计报表接口查询完成，"
                f"{current_range[0]} 至 {current_range[1]} 对比 "
                f"{comparison_range[0]} 至 {comparison_range[1]}，返回 {len(records)} 条记录"
            ),
        }

        grouped = _records_by_city(records)
        report_data_id = save_report_data_package(
            context=context,
            tool_name="query_city_standard_yoy_report",
            query={
                "cities": expanded_cities,
                "requested_cities": requested_cities,
                "time_point": current_range,
                "contrast_time": comparison_range,
                "ns_type": ns_type,
                "time_type": time_type,
                "pollutant_codes": effective_pollutants,
                "plan_type": plan_type,
                "data_source": data_source,
                "sand_type": sand_type,
                "revise_type": revise_type,
            },
            result=result,
            metadata=metadata,
            primary_view_name="cities",
            primary_name_field="city",
            primary_stats=grouped,
            extra_views={"raw": records, "result": records},
            package_kind="city_standard_yoy_report_api",
        )
        if report_data_id:
            metadata["report_data_id"] = report_data_id
            result["report_data_id"] = report_data_id
            result["summary"] += f" | 完整接口报表已保存为 report_data_id: {report_data_id}"
            result["registry_usage"] = {
                "cities": f'read_data_registry(data_id="{report_data_id}", view="cities")',
                "raw": f'read_data_registry(data_id="{report_data_id}", view="raw")',
                "result": f'read_data_registry(data_id="{report_data_id}", view="result")',
            }

        return result

    except Exception as exc:
        logger.error("query_city_standard_yoy_report_failed", error=str(exc), error_type=type(exc).__name__)
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {
                "tool_name": "query_city_standard_yoy_report",
                "error": str(exc),
                "request_payload": payload,
            },
            "summary": f"城市同比统计报表接口查询失败：{exc}",
        }


class QueryCityStandardReportTool(LLMTool):
    """城市新旧国标统计报表接口查询工具。"""

    def __init__(self):
        function_schema = {
            "name": "query_city_standard_report",
            "description": (
                "【第一优先级】查询广东省城市统计报表接口，直接使用联网接口返回的新/旧国标统计结果，"
                "不进行本地日报重算。用于综合指数、达标/超标天数、污染物统计浓度、首要污染物、排名等统计报表。"
                "ns_type=2 表示新国标；ns_type=1 表示旧国标。"
                "完整接口结果保存到 report_data_id，可用 read_data_registry 读取 cities/raw/result 视图。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表；可传广东省、全省、珠三角、非珠三角等区域别名；不传则由接口返回默认范围",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
                    },
                    "ns_type": {
                        "type": "integer",
                        "description": "接口标准类型：2=新国标，1=旧国标",
                        "enum": [1, 2],
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "报表类型：3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间；默认8",
                        "enum": [3, 4, 5, 7, 8],
                        "default": 8,
                    },
                    "pollutant_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "接口字段过滤列表，如 ['so2','compositeIndex']；默认不传/为空，接口返回全部字段。仅当需要主动筛选字段时传入",
                    },
                    "plan_type": {"type": "integer", "description": "接口 planType，默认0", "default": 0},
                    "data_source": {
                        "type": "integer",
                        "description": "数据源：0原始实况，1审核实况，2原始标况，3审核标况；默认1",
                        "enum": [0, 1, 2, 3],
                        "default": 1,
                    },
                    "sand_type": {
                        "type": "integer",
                        "description": "扣沙类型：0不扣沙，1扣沙；默认1",
                        "enum": [0, 1],
                        "default": 1,
                    },
                    "revise_type": {"type": "integer", "description": "接口 ReviseType，默认0", "default": 0},
                    "skip_count": {"type": "integer", "description": "分页 skipCount，默认0", "default": 0},
                    "max_result_count": {"type": "integer", "description": "分页 maxResultCount，默认200", "default": 200},
                },
                "required": ["start_time", "end_time"],
            },
        }
        super().__init__(
            name="query_city_standard_report",
            description="Query Guangdong city standard statistical report via Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        start_time = kwargs.get("start_time") or kwargs.get("start_date")
        end_time = kwargs.get("end_time") or kwargs.get("end_date")
        if not start_time or not end_time:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_city_standard_report", "error": "Missing time range"},
                "summary": "缺少必需参数：start_time/end_time",
            }
        try:
            datetime.strptime(_normalize_datetime(start_time), "%Y-%m-%d %H:%M:%S")
            datetime.strptime(_normalize_datetime(end_time, end_of_day=True), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_city_standard_report", "error": "Invalid datetime format"},
                "summary": "时间格式错误，期望 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
            }

        ns_type = kwargs.get("ns_type")
        if ns_type is None:
            ns_type = 2

        return await execute_query_city_standard_report(
            cities=kwargs.get("cities"),
            start_time=start_time,
            end_time=end_time,
            ns_type=int(ns_type),
            time_type=int(kwargs.get("time_type", 8)),
            pollutant_codes=kwargs.get("pollutant_codes"),
            plan_type=int(kwargs.get("plan_type", 0)),
            data_source=int(kwargs.get("data_source", 1)),
            sand_type=int(kwargs.get("sand_type", 1)),
            revise_type=int(kwargs.get("revise_type", 0)),
            skip_count=int(kwargs.get("skip_count", 0)),
            max_result_count=int(kwargs.get("max_result_count", 200)),
            context=context,
        )


class QueryCityStandardYoyReportTool(LLMTool):
    """城市新旧国标同比/环比统计报表接口查询工具。"""

    def __init__(self):
        function_schema = {
            "name": "query_city_standard_yoy_report",
            "description": (
                "【第一优先级】查询广东省城市同比/环比统计报表接口，直接调用联网接口"
                "GetReportForRangeCompareListFilterAsync 返回当前值、对比值、增幅和排名等字段，"
                "不再本地计算城市新/旧国标同比统计报表。"
                "ns_type=2 表示新国标；ns_type=1 表示旧国标。"
                "适用于同比、环比、双时段对比、变化率、改善/恶化分析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表；可传广东省、全省、珠三角、非珠三角等区域别名；不传则由接口返回默认范围",
                    },
                    "time_point": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "当前时间范围，如 ['2026-05-08 00:00:00','2026-05-14 00:00:00']",
                    },
                    "contrast_time": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "对比时间范围，如 ['2025-05-08 00:00:00','2025-05-14 00:00:00']",
                    },
                    "query_period": {
                        "type": "object",
                        "description": "兼容旧对比工具的当前时段对象，包含 start_date/end_date",
                    },
                    "comparison_period": {
                        "type": "object",
                        "description": "兼容旧对比工具的对比时段对象，包含 start_date/end_date",
                    },
                    "ns_type": {
                        "type": "integer",
                        "description": "接口标准类型：2=新国标，1=旧国标",
                        "enum": [1, 2],
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "报表类型：4=月报, 8=任意时间；默认8",
                        "enum": [4, 8],
                        "default": 8,
                    },
                    "pollutant_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "接口字段过滤列表，如 ['so2']；不传则返回接口默认字段",
                    },
                    "plan_type": {"type": "integer", "description": "接口 planType，默认0", "default": 0},
                    "data_source": {
                        "type": "integer",
                        "description": "数据源：0原始实况，1审核实况，2原始标况，3审核标况；默认1",
                        "enum": [0, 1, 2, 3],
                        "default": 1,
                    },
                    "sand_type": {
                        "type": "integer",
                        "description": "扣沙类型：0不扣沙，1扣沙；默认1",
                        "enum": [0, 1],
                        "default": 1,
                    },
                    "revise_type": {"type": "integer", "description": "接口 ReviseType，默认0", "default": 0},
                    "skip_count": {"type": "integer", "description": "分页 skipCount，默认0", "default": 0},
                    "max_result_count": {"type": "integer", "description": "分页 maxResultCount，默认200", "default": 200},
                },
                "required": [],
            },
        }
        super().__init__(
            name="query_city_standard_yoy_report",
            description="Query Guangdong city standard YoY comparative report via Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        time_point = kwargs.get("time_point")
        contrast_time = kwargs.get("contrast_time")
        if not time_point:
            query_period = kwargs.get("query_period") or {}
            if query_period.get("start_date") and query_period.get("end_date"):
                time_point = [query_period["start_date"], query_period["end_date"]]
        if not contrast_time:
            comparison_period = kwargs.get("comparison_period") or {}
            if comparison_period.get("start_date") and comparison_period.get("end_date"):
                contrast_time = [comparison_period["start_date"], comparison_period["end_date"]]

        if not isinstance(time_point, list) or not isinstance(contrast_time, list):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_city_standard_yoy_report", "error": "Missing time ranges"},
                "summary": "缺少必需参数：time_point/contrast_time，或 query_period/comparison_period",
            }

        try:
            for value, end_of_day in [
                (time_point[0], False),
                (time_point[1], True),
                (contrast_time[0], False),
                (contrast_time[1], True),
            ]:
                datetime.strptime(_normalize_datetime(value, end_of_day=end_of_day), "%Y-%m-%d %H:%M:%S")
        except (IndexError, ValueError):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_city_standard_yoy_report", "error": "Invalid datetime format"},
                "summary": "时间格式错误，期望 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，且每个时间范围包含起止两个值",
            }

        ns_type = kwargs.get("ns_type")
        if ns_type is None:
            ns_type = 2

        return await execute_query_city_standard_yoy_report(
            cities=kwargs.get("cities"),
            time_point=time_point,
            contrast_time=contrast_time,
            ns_type=int(ns_type),
            time_type=int(kwargs.get("time_type", 8)),
            pollutant_codes=kwargs.get("pollutant_codes"),
            plan_type=int(kwargs.get("plan_type", 0)),
            data_source=int(kwargs.get("data_source", 1)),
            sand_type=int(kwargs.get("sand_type", 1)),
            revise_type=int(kwargs.get("revise_type", 0)),
            skip_count=int(kwargs.get("skip_count", 0)),
            max_result_count=int(kwargs.get("max_result_count", 200)),
            context=context,
        )
