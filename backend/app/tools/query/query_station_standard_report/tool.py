"""
站点新旧国标统计报表接口查询工具。

直接调用广东联网统计报表接口，通过 nsType 选择新/旧国标口径，
不再基于本地站点日报数据重算统计指标。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.agent.context.execution_context import ExecutionContext
from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.tools.base import LLMTool, ToolCategory
from app.tools.query.query_city_standard_report.tool import (
    _extract_report_records,
    _normalize_datetime,
    _normalize_pollutant_codes,
)
from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
from app.tools.query.report_data_package import save_report_data_package

logger = structlog.get_logger()


def _station_name_from_record(record: Dict[str, Any]) -> str:
    return str(
        record.get("stationName")
        or record.get("StationName")
        or record.get("name")
        or record.get("Name")
        or record.get("stationCode")
        or record.get("StationCode")
        or record.get("uniqueCode")
        or record.get("UniqueCode")
        or ""
    ).strip()


def _records_by_station(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for idx, record in enumerate(records):
        name = _station_name_from_record(record) or f"record_{idx + 1}"
        grouped[name] = record
    return grouped


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        key = str(value).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _direct_station_code(value: str) -> Optional[str]:
    raw = str(value).strip()
    if not raw:
        return None
    upper = raw.upper()
    if len(upper) >= 5 and upper[:-1].isdigit() and upper[-1].isalpha():
        return upper
    return None


def _build_station_codes(
    *,
    cities: Optional[List[str]],
    stations: Optional[List[str]],
    station_type: Optional[str],
    tool_name: str,
) -> tuple[List[str], Dict[str, Any], Optional[Dict[str, Any]]]:
    requested_cities = list(cities or [])
    requested_stations = list(stations or [])
    station_codes: List[str] = []
    station_type_metadata: Dict[str, Any] = {}

    if requested_stations:
        direct_codes = [_direct_station_code(station) for station in requested_stations]
        unresolved_names = [
            station for station, code in zip(requested_stations, direct_codes) if not code
        ]
        station_codes.extend([code for code in direct_codes if code])
        if unresolved_names:
            station_codes.extend(
                QueryGDSuncereDataTool.geo_resolver.resolve_station_codes(unresolved_names)
            )

    if requested_cities:
        if station_type:
            try:
                city_station_codes, station_type_metadata = (
                    QueryGDSuncereDataTool.geo_resolver.resolve_station_codes_by_type(
                        station_type,
                        requested_cities,
                    )
                )
            except ValueError as exc:
                return [], {}, {
                    "status": "failed",
                    "success": False,
                    "data": [],
                    "result": [],
                    "metadata": {
                        "tool_name": tool_name,
                        "requested_cities": requested_cities,
                        "requested_stations": requested_stations,
                        "station_type": station_type,
                        "error": str(exc),
                    },
                    "summary": str(exc),
                }
            station_codes.extend(city_station_codes)
        else:
            station_codes.extend(
                QueryGDSuncereDataTool.geo_resolver.resolve_station_codes_by_city(requested_cities)
            )

    station_codes = _dedupe(station_codes)
    if (requested_cities or requested_stations) and not station_codes:
        return [], station_type_metadata, {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {
                "tool_name": tool_name,
                "requested_cities": requested_cities,
                "requested_stations": requested_stations,
                "station_type": station_type,
                "error": "No valid station codes found",
            },
            "summary": "未找到有效站点编码，请检查城市、站点名称或站点类型",
        }

    return station_codes, station_type_metadata, None


def _resolve_ns_type(kwargs: Dict[str, Any]) -> int:
    ns_type = kwargs.get("ns_type")
    if ns_type is not None:
        return int(ns_type)
    standard_type = str(kwargs.get("standard_type") or "new").lower()
    return 1 if standard_type in {"old", "旧", "旧国标"} else 2


def execute_query_station_standard_report(
    *,
    cities: Optional[List[str]] = None,
    stations: Optional[List[str]] = None,
    start_time: str,
    end_time: str,
    station_type: Optional[str] = "国控",
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
    """查询站点统计报表。ns_type: 2=新国标，1=旧国标。"""
    tool_name = "query_station_standard_report"
    if ns_type not in (1, 2):
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": tool_name, "error": "Invalid ns_type"},
            "summary": "ns_type 参数错误：1=旧国标，2=新国标",
        }

    station_codes, station_type_metadata, code_error = _build_station_codes(
        cities=cities,
        stations=stations,
        station_type=station_type if cities else None,
        tool_name=tool_name,
    )
    if code_error:
        return code_error

    start = _normalize_datetime(start_time)
    end = _normalize_datetime(end_time, end_of_day=True)
    effective_pollutants = _normalize_pollutant_codes(pollutant_codes)
    payload: Dict[str, Any] = {
        "skipCount": skip_count,
        "maxResultCount": max_result_count,
        "TimeType": time_type,
        "AreaType": 0,
        "TimePoint": [start, end],
        "StationCode": station_codes,
        "planType": plan_type,
        "dataSource": data_source,
        "sandType": sand_type,
        "ReviseType": revise_type,
        "nsType": ns_type,
    }
    if effective_pollutants:
        payload["PollutantCode"] = effective_pollutants

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
                    "tool_name": tool_name,
                    "api_state": response.get("state"),
                    "api_msg": response.get("msg"),
                    "request_payload": payload,
                },
                "summary": f"站点统计报表接口查询失败：{response.get('msg') or '未知错误'}",
            }

        records = _extract_report_records(response.get("result"))
        standard_label = "新国标" if ns_type == 2 else "旧国标"
        metadata = {
            "schema_version": "v2.0",
            "tool_name": tool_name,
            "standard": standard_label,
            "ns_type": ns_type,
            "cities": cities or [],
            "stations": stations or [],
            "station_type": station_type,
            "station_type_metadata": station_type_metadata,
            "station_codes": station_codes,
            "time_range": f"{start} to {end}",
            "time_type": time_type,
            "area_type": 0,
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
            "summary": f"{standard_label}站点统计报表接口查询完成，{start} 至 {end}，返回 {len(records)} 条记录",
        }

        grouped = _records_by_station(records)
        report_data_id = save_report_data_package(
            context=context,
            tool_name=tool_name,
            query={
                "cities": cities or [],
                "stations": stations or [],
                "start_time": start,
                "end_time": end,
                "station_type": station_type,
                "station_codes": station_codes,
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
            primary_view_name="stations",
            primary_name_field="station",
            primary_stats=grouped,
            extra_views={"raw": records, "result": records},
            package_kind="station_standard_report_api",
        )
        if report_data_id:
            metadata["report_data_id"] = report_data_id
            result["report_data_id"] = report_data_id
            result["summary"] += f" | 完整接口报表已保存为 report_data_id: {report_data_id}"
            result["registry_usage"] = {
                "stations": f'read_data_registry(data_id="{report_data_id}", view="stations")',
                "raw": f'read_data_registry(data_id="{report_data_id}", view="raw")',
                "result": f'read_data_registry(data_id="{report_data_id}", view="result")',
            }
        return result
    except Exception as exc:
        logger.error("query_station_standard_report_failed", error=str(exc), error_type=type(exc).__name__)
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": tool_name, "error": str(exc), "request_payload": payload},
            "summary": f"站点统计报表接口查询失败：{exc}",
        }


def execute_query_station_standard_yoy_report(
    *,
    cities: Optional[List[str]] = None,
    stations: Optional[List[str]] = None,
    time_point: List[str],
    contrast_time: List[str],
    station_type: Optional[str] = "国控",
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
    """查询站点同比/环比统计报表。ns_type: 2=新国标，1=旧国标。"""
    tool_name = "query_station_standard_yoy_report"
    if ns_type not in (1, 2):
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": tool_name, "error": "Invalid ns_type"},
            "summary": "ns_type 参数错误：1=旧国标，2=新国标",
        }
    if len(time_point) != 2 or len(contrast_time) != 2:
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": tool_name, "error": "Invalid time ranges"},
            "summary": "time_point 和 contrast_time 都必须是两个时间组成的数组",
        }

    station_codes, station_type_metadata, code_error = _build_station_codes(
        cities=cities,
        stations=stations,
        station_type=station_type if cities else None,
        tool_name=tool_name,
    )
    if code_error:
        return code_error

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
        "AreaType": 0,
        "TimePoint": current_range,
        "ContrastTime": comparison_range,
        "StationCode": station_codes,
        "planType": plan_type,
        "dataSource": data_source,
        "sandType": sand_type,
        "ReviseType": revise_type,
        "nsType": ns_type,
    }
    if effective_pollutants:
        payload["PollutantCode"] = effective_pollutants

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
                    "tool_name": tool_name,
                    "api_state": response.get("state"),
                    "api_msg": response.get("msg"),
                    "request_payload": payload,
                },
                "summary": f"站点同比统计报表接口查询失败：{response.get('msg') or '未知错误'}",
            }

        records = _extract_report_records(response.get("result"))
        standard_label = "新国标" if ns_type == 2 else "旧国标"
        metadata = {
            "schema_version": "v2.0",
            "tool_name": tool_name,
            "standard": standard_label,
            "ns_type": ns_type,
            "cities": cities or [],
            "stations": stations or [],
            "station_type": station_type,
            "station_type_metadata": station_type_metadata,
            "station_codes": station_codes,
            "time_point": current_range,
            "contrast_time": comparison_range,
            "time_type": time_type,
            "area_type": 0,
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
                f"{standard_label}站点同比统计报表接口查询完成，"
                f"{current_range[0]} 至 {current_range[1]} 对比 "
                f"{comparison_range[0]} 至 {comparison_range[1]}，返回 {len(records)} 条记录"
            ),
        }

        grouped = _records_by_station(records)
        report_data_id = save_report_data_package(
            context=context,
            tool_name=tool_name,
            query={
                "cities": cities or [],
                "stations": stations or [],
                "time_point": current_range,
                "contrast_time": comparison_range,
                "station_type": station_type,
                "station_codes": station_codes,
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
            primary_view_name="stations",
            primary_name_field="station",
            primary_stats=grouped,
            extra_views={"raw": records, "result": records},
            package_kind="station_standard_yoy_report_api",
        )
        if report_data_id:
            metadata["report_data_id"] = report_data_id
            result["report_data_id"] = report_data_id
            result["summary"] += f" | 完整接口报表已保存为 report_data_id: {report_data_id}"
            result["registry_usage"] = {
                "stations": f'read_data_registry(data_id="{report_data_id}", view="stations")',
                "raw": f'read_data_registry(data_id="{report_data_id}", view="raw")',
                "result": f'read_data_registry(data_id="{report_data_id}", view="result")',
            }
        return result
    except Exception as exc:
        logger.error("query_station_standard_yoy_report_failed", error=str(exc), error_type=type(exc).__name__)
        return {
            "status": "failed",
            "success": False,
            "data": [],
            "result": [],
            "metadata": {"tool_name": tool_name, "error": str(exc), "request_payload": payload},
            "summary": f"站点同比统计报表接口查询失败：{exc}",
        }


class QueryStationStandardReportTool(LLMTool):
    """站点新旧国标统计报表接口查询工具。"""

    def __init__(self):
        function_schema = {
            "name": "query_station_standard_report",
            "description": (
                "【第一优先级】查询广东省站点统计报表接口，直接使用联网接口返回的新/旧国标统计结果，"
                "不进行本地日报重算。用于站点综合指数、达标/超标天数、污染物统计浓度、首要污染物、排名等统计报表。"
                "standard_type='new' 或 ns_type=2 表示新国标；standard_type='old' 或 ns_type=1 表示旧国标。"
                "cities 会按 station_type 展开站点，默认国控；也可直接传 stations 或站点编码。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，可自动展开站点"},
                    "stations": {"type": "array", "items": {"type": "string"}, "description": "站点名称或站点编码列表"},
                    "station_type": {"type": "string", "description": "站点类型，仅 cities 时生效，默认国控"},
                    "start_time": {"type": "string", "description": "开始时间，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                    "end_time": {"type": "string", "description": "结束时间，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                    "start_date": {"type": "string", "description": "兼容字段，等同 start_time"},
                    "end_date": {"type": "string", "description": "兼容字段，等同 end_time"},
                    "standard_type": {"type": "string", "description": "new=新国标，old=旧国标", "enum": ["new", "old"]},
                    "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标", "enum": [1, 2]},
                    "time_type": {"type": "integer", "description": "3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间；默认8", "enum": [3, 4, 5, 7, 8]},
                    "pollutant_codes": {"type": "array", "items": {"type": "string"}, "description": "接口字段过滤列表，不传则返回常用统计字段"},
                    "plan_type": {"type": "integer", "description": "接口 planType，默认0"},
                    "data_source": {"type": "integer", "description": "0原始实况，1审核实况，2原始标况，3审核标况；默认1", "enum": [0, 1, 2, 3]},
                    "sand_type": {"type": "integer", "description": "0不扣沙，1扣沙；默认1", "enum": [0, 1]},
                    "revise_type": {"type": "integer", "description": "接口 ReviseType，默认0"},
                    "skip_count": {"type": "integer", "description": "分页 skipCount，默认0"},
                    "max_result_count": {"type": "integer", "description": "分页 maxResultCount，默认200"},
                },
                "required": [],
            },
        }
        super().__init__(
            name="query_station_standard_report",
            description="Query Guangdong station standard statistical report via Suncere API",
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
                "metadata": {"tool_name": "query_station_standard_report", "error": "Missing time range"},
                "summary": "缺少必需参数：start_time/end_time",
            }
        if not kwargs.get("cities") and not kwargs.get("stations"):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_station_standard_report", "error": "Missing cities or stations"},
                "summary": "必须提供 cities 或 stations。为避免数据量过大，不支持默认全省站点查询。",
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
                "metadata": {"tool_name": "query_station_standard_report", "error": "Invalid datetime format"},
                "summary": "时间格式错误，期望 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
            }

        return execute_query_station_standard_report(
            cities=kwargs.get("cities"),
            stations=kwargs.get("stations"),
            start_time=start_time,
            end_time=end_time,
            station_type=kwargs.get("station_type", "国控"),
            ns_type=_resolve_ns_type(kwargs),
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


class QueryStationStandardYoyReportTool(LLMTool):
    """站点新旧国标同比/环比统计报表接口查询工具。"""

    def __init__(self):
        function_schema = {
            "name": "query_station_standard_yoy_report",
            "description": (
                "【第一优先级】查询广东省站点同比/环比统计报表接口，直接调用联网接口返回当前值、对比值、增幅和排名等字段。"
                "不再本地计算站点新/旧国标双时段统计报表。standard_type='new' 或 ns_type=2 表示新国标；"
                "standard_type='old' 或 ns_type=1 表示旧国标。适用于站点同比、环比、变化率、改善/恶化分析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，可自动展开站点"},
                    "stations": {"type": "array", "items": {"type": "string"}, "description": "站点名称或站点编码列表"},
                    "station_type": {"type": "string", "description": "站点类型，仅 cities 时生效，默认国控"},
                    "time_point": {"type": "array", "items": {"type": "string"}, "description": "当前时间范围，如 ['2026-05-08 00:00:00','2026-05-14 00:00:00']"},
                    "contrast_time": {"type": "array", "items": {"type": "string"}, "description": "对比时间范围，如 ['2025-05-08 00:00:00','2025-05-14 00:00:00']"},
                    "query_period": {"type": "object", "description": "兼容字段，当前时段对象，包含 start_date/end_date"},
                    "comparison_period": {"type": "object", "description": "兼容字段，对比时段对象，包含 start_date/end_date"},
                    "standard_type": {"type": "string", "description": "new=新国标，old=旧国标", "enum": ["new", "old"]},
                    "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标", "enum": [1, 2]},
                    "time_type": {"type": "integer", "description": "4=月报, 8=任意时间；默认8", "enum": [4, 8]},
                    "pollutant_codes": {"type": "array", "items": {"type": "string"}, "description": "接口字段过滤列表，不传返回接口默认字段"},
                    "plan_type": {"type": "integer", "description": "接口 planType，默认0"},
                    "data_source": {"type": "integer", "description": "0原始实况，1审核实况，2原始标况，3审核标况；默认1", "enum": [0, 1, 2, 3]},
                    "sand_type": {"type": "integer", "description": "0不扣沙，1扣沙；默认1", "enum": [0, 1]},
                    "revise_type": {"type": "integer", "description": "接口 ReviseType，默认0"},
                    "skip_count": {"type": "integer", "description": "分页 skipCount，默认0"},
                    "max_result_count": {"type": "integer", "description": "分页 maxResultCount，默认200"},
                },
                "required": [],
            },
        }
        super().__init__(
            name="query_station_standard_yoy_report",
            description="Query Guangdong station standard YoY comparative report via Suncere API",
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
                "metadata": {"tool_name": "query_station_standard_yoy_report", "error": "Missing time ranges"},
                "summary": "缺少必需参数：time_point/contrast_time，或 query_period/comparison_period",
            }
        if not kwargs.get("cities") and not kwargs.get("stations"):
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_station_standard_yoy_report", "error": "Missing cities or stations"},
                "summary": "必须提供 cities 或 stations。为避免数据量过大，不支持默认全省站点查询。",
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
                "metadata": {"tool_name": "query_station_standard_yoy_report", "error": "Invalid datetime format"},
                "summary": "时间格式错误，期望 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，且每个时间范围包含起止两个值",
            }

        return execute_query_station_standard_yoy_report(
            cities=kwargs.get("cities"),
            stations=kwargs.get("stations"),
            time_point=time_point,
            contrast_time=contrast_time,
            station_type=kwargs.get("station_type", "国控"),
            ns_type=_resolve_ns_type(kwargs),
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
