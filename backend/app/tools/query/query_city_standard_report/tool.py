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

DEFAULT_NEW_STANDARD_START = datetime(2025, 1, 1)
DEFAULT_OLD_STANDARD_END = datetime(2024, 12, 31, 23, 59, 59)


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

# 区域别名列表（查询这些时不传StationCode，返回全部27条）
REGION_ALIASES = ["全省", "广东省", "珠三角", "非珠三角", "粤东", "粤西", "粤北", "粤东西北"]

# 全部21个城市
ALL_CITIES = GUANGDONG_REGIONS["全省"]

# 报告展示常用顺序。不要用接口默认行政编码顺序让 Agent 再手工重排。
PUBLIC_REPORT_CITY_ORDER = [
    "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "河源", "梅州", "惠州", "汕尾",
    "东莞", "中山", "江门", "阳江", "湛江", "茂名", "肇庆", "清远", "潮州", "揭阳", "云浮",
]
PUBLIC_REPORT_REGION_ORDER = ["粤东", "粤西", "粤北", "珠三角", "非珠三角", "粤东西北", "全省"]
PUBLIC_REPORT_REGION_ALIASES = {"广东省": "全省", "粤东西北": "非珠三角"}


def _parse_report_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    return datetime.strptime(_normalize_datetime(value, end_of_day=end_of_day), "%Y-%m-%d %H:%M:%S")


def _default_ns_type_for_range(start_time: str, end_time: str) -> Optional[int]:
    start_dt = _parse_report_datetime(start_time)
    end_dt = _parse_report_datetime(end_time, end_of_day=True)
    if end_dt < DEFAULT_NEW_STANDARD_START:
        return 1
    if start_dt >= DEFAULT_NEW_STANDARD_START:
        return 2
    return None


def _resolve_ns_type(ns_type: Optional[Any], start_time: str, end_time: str) -> Any:
    if ns_type is not None:
        try:
            return int(ns_type)
        except (TypeError, ValueError):
            return ns_type
    return _default_ns_type_for_range(start_time, end_time)


def _build_default_standard_segments(start_time: str, end_time: str) -> List[Dict[str, Any]]:
    start = _normalize_datetime(start_time)
    end = _normalize_datetime(end_time, end_of_day=True)
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    if start_dt > end_dt:
        return []
    if end_dt < DEFAULT_NEW_STANDARD_START:
        return [{"ns_type": 1, "standard": "旧国标", "start_time": start, "end_time": end}]
    if start_dt >= DEFAULT_NEW_STANDARD_START:
        return [{"ns_type": 2, "standard": "新国标", "start_time": start, "end_time": end}]
    return [
        {
            "ns_type": 1,
            "standard": "旧国标",
            "start_time": start,
            "end_time": DEFAULT_OLD_STANDARD_END.strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "ns_type": 2,
            "standard": "新国标",
            "start_time": DEFAULT_NEW_STANDARD_START.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end,
        },
    ]


STANDARD_REPORT_FIELD_DESCRIPTIONS: Dict[str, str] = {
    "timePoint": "统计时间范围，通常是接口返回的区间字符串。",
    "sO2/nO2/pM2_5/pM10/co/o3_8h": "污染物统计浓度；PM2.5 对应 pM2_5，O3 通常看臭氧日最大8小时滑动平均 o3_8h。",
    "no/nOx/o3/aqi": "接口可能返回的扩展字段；部分报表中可能为空，回答时应以非空字段为准。",
    "primaryPollutant": "统计期内首要污染物汇总字段。",
    "*_PrimaryPollutantDays": "该污染物作为首要污染物的天数，不等同于该污染物超标天数。",
    "*_PrimaryPollutantRate": "该污染物作为首要污染物的天数占比，单位通常为百分比。",
    "*_PrimaryPollutantOverDays": "该污染物作为首要污染物且当天空气质量超标的天数。",
    "*_PrimaryPollutantOverRate": "该污染物作为首要污染物且超标的天数占比，单位通常为百分比。",
    "*_SingleIndex": "该污染物单项指数，用于判断污染贡献；不是污染物浓度。",
    "oneLevel/twoLevel/threeLevel/fourLevel/fiveLevel/sixLevel": "空气质量一级到六级天数；一级、二级通常合计为优良天数，三级及以上通常为超标天数。",
    "*LevelRate": "对应空气质量等级天数占比，单位通常为百分比。",
    "fineDays/fineRate": "优良天数及优良率，通常对应一级+二级天数及其占比。",
    "overDays/overRate": "超标天数及超标率，通常对应三级及以上天数及其占比。",
    "seriousDays/seriousRate": "重污染及以上天数和占比。",
    "compositeIndex": "综合指数，数值越低通常表示空气质量越好。",
    "maxIndex": "统计期内最大单项指数，不是最大污染物浓度。",
    "rank/comprehensiveRank/pM25Rank": "排名字段；具体排序方向依接口口径，回答涉及最好/最差时需谨慎核对上下文。",
    "comprehensiveChangeRate": "综合指数变化率；负值通常表示综合指数下降，空气质量改善。",
    "comprehensiveChangeRank": "综合指数变化排名；排序方向依接口口径。",
    "pM2_5_Decimal_Increase": (
        "PM2.5 阶段均值同比变化率。按新标准，PM2.5 统计评价使用阶段均值 "
        "pM2_5_Decimal，因此 PM2.5 同比评价应优先使用该字段。"
    ),
    "pM2_5_Decimal_Compare": (
        "PM2.5 对比期阶段均值。若同比接口未直接返回该字段，则由对比期单时段报表的 "
        "pM2_5_Decimal 补充。"
    ),
    "pM2_5_Increase": "接口原始 PM2.5 增幅字段，通常基于修约后的 pM2_5 计算；新标准评价口径不要优先使用该字段。",
    "*_Max": "统计期内该污染物最大值。",
    "*_Decimal": "该污染物未取整或保留小数的统计浓度；普通污染物字段多为展示取整值。",
    "qualityType": "空气质量类别/评价类型，接口可能为空；为空时不应强行解读。",
    "dateArange": "接口遗留字段，含义不稳定；为空时忽略。",
}


def get_standard_report_field_descriptions(report_level: str, *, comparative: bool = False) -> Dict[str, str]:
    descriptions = dict(STANDARD_REPORT_FIELD_DESCRIPTIONS)
    if report_level == "city":
        descriptions.update(
            {
                "cityCode/cityName": "城市编码和城市名称。",
                "districtCode/districtName": "城市报表中通常与城市编码/城市名称一致，不一定代表区县。",
                "uniqueCode/stationCode/stationName": "城市报表中通常复用为城市编码/城市名称，不代表真实监测站点。",
            }
        )
    else:
        descriptions.update(
            {
                "cityCode/cityName": "站点所属城市编码和城市名称。",
                "districtCode/districtName": "站点所属区县编码和区县名称，接口也可能返回城市级值。",
                "uniqueCode/stationCode/stationName": "站点唯一编码、站点编码和站点名称。",
            }
        )
    if comparative:
        descriptions.update(
            {
                "time_point": "当前统计时段，见 metadata.time_point。",
                "contrast_time": "对比统计时段，见 metadata.contrast_time。",
                "reporting view limitations": (
                    "reporting/data 是报告口径精简视图；排名明细、单项指数、首要污染物天数/占比、"
                    "各等级天数/占比、最大值、小数字段等完整接口字段不在 reporting 中，"
                    "需要读取 raw/result/cities 视图。"
                ),
                "*ChangeRate": "变化率字段；污染浓度或综合指数下降通常表示改善，上升通常表示恶化，需结合具体指标判断。",
                "*ChangeRank": "变化排名字段；排序方向依接口口径。",
            }
        )
    return descriptions


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


def _normalize_increase_dash_values(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert API zero-change placeholders on *_Increase fields to numeric 0."""
    normalized_records: List[Dict[str, Any]] = []
    for record in records:
        normalized_record = dict(record)
        for field_name, value in record.items():
            normalized_field_name = str(field_name).lower()
            if (
                value == "--"
                and (
                    normalized_field_name.endswith("_increase")
                    or normalized_field_name.endswith("_increas")
                )
            ):
                normalized_record[field_name] = 0
        normalized_records.append(normalized_record)
    return normalized_records


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


def _calculate_change_rate(current_value: Any, comparison_value: Any) -> Optional[float]:
    current = _to_float(current_value)
    comparison = _to_float(comparison_value)
    if current is None or comparison is None or comparison == 0:
        return None
    return round((current - comparison) / comparison * 100, 1)


def _first_present(record: Dict[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        if field_name in record and record.get(field_name) is not None:
            value = record.get(field_name)
            # 过滤 API 返回的特殊字符，表示"无法计算"或"无数据"
            if value == "—" or value == "—" or value == "--" or value == "" or value == "-":
                return None
            return value
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_delta_only_record(record: Dict[str, Any]) -> bool:
    """Detect rows that carry comparison deltas instead of current values."""
    composite_index = _to_float(_first_present(record, "compositeIndex", "CompositeIndex"))
    if composite_index is not None and composite_index < 0:
        return True

    pm25 = _to_float(_first_present(record, "pM2_5", "PM2_5"))
    if pm25 is not None and pm25 < 0 and _first_present(record, "pM2_5_Increase", "PM2_5_Increase") is None:
        return True

    return False


def _nonnegative_measure(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is not None and numeric < 0:
        return None
    return value


def _pm25_reporting_value(record: Dict[str, Any]) -> Any:
    value = _first_present(record, "pM2_5_Decimal", "PM2_5_Decimal")
    if value is None:
        single_index = _first_present(record, "pM2_5_SingleIndex", "PM2_5_SingleIndex")
        if single_index is not None:
            try:
                value = float(single_index) * 30
            except (TypeError, ValueError):
                value = None
    if value is None:
        value = _first_present(record, "pM2_5", "PM2_5")
    if value is None:
        return None
    numeric = _to_float(value)
    if numeric is None:
        return value
    if numeric < 0:
        return None
    return round(numeric, 1)


def _pm25_reporting_compare_value(record: Dict[str, Any]) -> Any:
    value = _first_present(record, "pM2_5_Decimal_Compare", "PM2_5_Decimal_Compare")
    if value is None:
        value = _first_present(record, "pM2_5_Compare", "PM2_5_Compare")
    numeric = _to_float(value)
    if numeric is None:
        return value
    if numeric < 0:
        return None
    return round(numeric, 1)


def _add_if_present(target: Dict[str, Any], label: str, value: Any) -> None:
    if value is not None:
        target[label] = value


def _add_measure_if_present(target: Dict[str, Any], label: str, value: Any) -> None:
    _add_if_present(target, label, _nonnegative_measure(value))


def _build_reporting_record(record: Dict[str, Any], *, name_label: str, name_value: str) -> Dict[str, Any]:
    """Build the default public-reporting view.

    Raw API fields stay in raw/result views. This view uses the field choices
    required by public disclosure: PM2.5 from pM2_5_Decimal with one decimal,
    and other pollutants from their standard concentration fields.
    """
    row: Dict[str, Any] = {}
    _add_if_present(row, name_label, name_value)
    _add_if_present(row, "城市编码", _first_present(record, "cityCode", "CityCode", "districtCode", "DistrictCode"))
    _add_if_present(row, "站点编码", _first_present(record, "stationCode", "StationCode", "uniqueCode", "UniqueCode"))
    _add_if_present(row, "统计时段", _first_present(record, "timePoint", "TimePoint"))

    _add_measure_if_present(row, "SO2", _first_present(record, "sO2", "SO2"))
    _add_measure_if_present(row, "NO2", _first_present(record, "nO2", "NO2"))
    _add_measure_if_present(row, "NO", _first_present(record, "no", "NO"))
    _add_measure_if_present(row, "NOx", _first_present(record, "nOx", "NOx"))
    _add_measure_if_present(row, "PM10", _first_present(record, "pM10", "PM10"))
    _add_measure_if_present(row, "CO", _first_present(record, "co", "CO"))
    _add_measure_if_present(row, "O3-8h", _first_present(record, "o3_8h", "O3_8h"))
    _add_if_present(row, "PM2.5", _pm25_reporting_value(record))

    _add_if_present(row, "SO2对比值", _first_present(record, "sO2_Compare", "SO2_Compare"))
    _add_if_present(row, "SO2同比变化率", _first_present(record, "sO2_Increase", "SO2_Increase"))
    _add_if_present(row, "NO2对比值", _first_present(record, "nO2_Compare", "NO2_Compare"))
    _add_if_present(row, "NO2同比变化率", _first_present(record, "nO2_Increase", "NO2_Increase"))
    _add_if_present(row, "PM10对比值", _first_present(record, "pM10_Compare", "PM10_Compare"))
    _add_if_present(row, "PM10同比变化率", _first_present(record, "pM10_Increase", "PM10_Increase"))
    _add_if_present(row, "CO对比值", _first_present(record, "cO_Compare", "CO_Compare", "co_Compare"))
    _add_if_present(row, "CO同比变化率", _first_present(record, "cO_Increase", "CO_Increase", "co_Increase"))
    _add_if_present(row, "O3-8h对比值", _first_present(record, "o3_8h_Compare", "O3_8h_Compare"))
    _add_if_present(row, "O3-8h同比变化率", _first_present(record, "o3_8h_Increase", "O3_8h_Increase"))
    _add_if_present(row, "PM2.5对比值", _pm25_reporting_compare_value(record))
    _add_if_present(row, "PM2.5接口原始对比值", _first_present(record, "pM2_5_Compare", "PM2_5_Compare"))
    _add_if_present(row, "AQI达标率", _first_present(record, "fineRate", "FineRate"))
    _add_if_present(row, "AQI达标天数", _first_present(record, "fineDays", "FineDays"))
    _add_if_present(row, "AQI同比变化", _first_present(record, "fineRate_Compare", "FineRate_Compare"))
    _add_if_present(row, "超标天数", _first_present(record, "overDays", "OverDays"))
    _add_if_present(row, "超标率", _first_present(record, "overRate", "OverRate"))
    _add_if_present(row, "O3超标天数", _first_present(record, "o3_8h_PrimaryPollutantOverDays", "O3_8h_PrimaryPollutantOverDays"))
    _add_if_present(row, "O3首要污染物天数", _first_present(record, "o3_8h_PrimaryPollutantDays", "O3_8h_PrimaryPollutantDays"))
    _add_if_present(row, "O3首要污染物占比", _first_present(record, "o3_8h_PrimaryPollutantRate", "O3_8h_PrimaryPollutantRate"))
    _add_if_present(row, "PM2.5首要污染物天数", _first_present(record, "pM2_5_PrimaryPollutantDays", "PM2_5_PrimaryPollutantDays"))
    _add_if_present(row, "PM2.5首要污染物占比", _first_present(record, "pM2_5_PrimaryPollutantRate", "PM2_5_PrimaryPollutantRate"))
    _add_if_present(row, "PM2.5同比变化率", _first_present(record, "pM2_5_Decimal_Increase", "PM2_5_Decimal_Increase"))
    _add_if_present(row, "PM2.5接口原始同比变化率", _first_present(record, "pM2_5_Increase", "PM2_5_Increase"))
    _add_if_present(row, "综合指数", _first_present(record, "compositeIndex", "CompositeIndex"))
    _add_if_present(row, "综合指数同比变化率", _first_present(record, "compositeIndex_Increase", "CompositeIndex_Increase", "comprehensiveChangeRate", "ComprehensiveChangeRate"))
    _add_if_present(row, "排名", _first_present(record, "rank", "Rank"))
    _add_if_present(row, "综合指数排名", _first_present(record, "comprehensiveRank", "ComprehensiveRank"))
    _add_if_present(row, "PM2.5排名", _first_present(record, "pM25Rank", "PM25Rank"))
    _add_if_present(row, "首要污染物", _first_present(record, "primaryPollutant", "PrimaryPollutant"))
    return row


def _sort_rows_by_name(rows: List[Dict[str, Any]], name_field: str, preferred_names: List[str]) -> List[Dict[str, Any]]:
    order = {name: idx for idx, name in enumerate(preferred_names)}
    return [
        row
        for _, row in sorted(
            enumerate(rows),
            key=lambda item: (order.get(str(item[1].get(name_field) or ""), len(order) + item[0]), item[0]),
        )
    ]


def build_city_reporting_records(
    records: List[Dict[str, Any]],
    preferred_cities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    reporting_rows = [
        _build_reporting_record(record, name_label="城市", name_value=_city_name_from_record(record) or f"record_{idx + 1}")
        for idx, record in enumerate(records)
        if not _is_delta_only_record(record)
    ]
    city_order = preferred_cities or PUBLIC_REPORT_CITY_ORDER
    return _sort_rows_by_name(reporting_rows, "城市", city_order + PUBLIC_REPORT_REGION_ORDER)


def _answer_ready_city_records(
    reporting_records: List[Dict[str, Any]],
    *,
    expanded_cities: List[str],
    requested_cities: List[str],
) -> List[Dict[str, Any]]:
    """Return the compact city rows the Agent should answer from directly."""
    preferred_names: List[str] = []
    for requested in requested_cities:
        name = PUBLIC_REPORT_REGION_ALIASES.get(requested, requested)
        if name in PUBLIC_REPORT_REGION_ORDER and name not in preferred_names:
            preferred_names.append(name)

    if preferred_names:
        wanted = set(preferred_names)
        filtered = [row for row in reporting_records if row.get("城市") in wanted]
        return _sort_rows_by_name(filtered, "城市", preferred_names)

    if expanded_cities:
        preferred_names.extend(expanded_cities)

    if not preferred_names:
        preferred_names = PUBLIC_REPORT_CITY_ORDER + PUBLIC_REPORT_REGION_ORDER

    wanted = set(preferred_names)
    filtered = [row for row in reporting_records if row.get("城市") in wanted]
    return _sort_rows_by_name(filtered, "城市", preferred_names)


def build_station_reporting_records(records: List[Dict[str, Any]], station_name_getter) -> List[Dict[str, Any]]:
    return [
        _build_reporting_record(record, name_label="站点", name_value=station_name_getter(record) or f"record_{idx + 1}")
        for idx, record in enumerate(records)
        if not _is_delta_only_record(record)
    ]


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


def _build_city_standard_report_payload(
    *,
    requested_cities: List[str],
    expanded_cities: List[str],
    city_codes: List[str],
    time_range: List[str],
    ns_type: int,
    pollutant_codes: Optional[List[str]],
    plan_type: int,
    data_source: int,
    sand_type: int,
    revise_type: int,
    skip_count: int,
    max_result_count: int,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "skipCount": skip_count,
        "maxResultCount": max_result_count,
        "TimeType": 8,
        "AreaType": 2,
        "TimePoint": time_range,
        "planType": plan_type,
        "dataSource": data_source,
        "sandType": sand_type,
        "ReviseType": revise_type,
        "nsType": ns_type,
    }
    effective_pollutants = _normalize_pollutant_codes(pollutant_codes)
    if effective_pollutants:
        payload["PollutantCode"] = effective_pollutants

    has_region_alias = any(city in REGION_ALIASES for city in requested_cities)
    is_all_cities = set(expanded_cities) == set(ALL_CITIES)
    should_send_station_code = city_codes and not has_region_alias and not is_all_cities
    if should_send_station_code:
        payload["StationCode"] = city_codes
    return payload


def _fetch_city_standard_records_for_range(
    *,
    requested_cities: List[str],
    expanded_cities: List[str],
    city_codes: List[str],
    time_range: List[str],
    ns_type: int,
    plan_type: int,
    data_source: int,
    sand_type: int,
    revise_type: int,
    skip_count: int,
    max_result_count: int,
) -> List[Dict[str, Any]]:
    payload = _build_city_standard_report_payload(
        requested_cities=requested_cities,
        expanded_cities=expanded_cities,
        city_codes=city_codes,
        time_range=time_range,
        ns_type=ns_type,
        pollutant_codes=None,
        plan_type=plan_type,
        data_source=data_source,
        sand_type=sand_type,
        revise_type=revise_type,
        skip_count=skip_count,
        max_result_count=max_result_count,
    )
    api_client = get_gd_suncere_api_client()
    response = api_client._make_request(
        "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync",
        payload,
        method="POST",
        timeout=60,
    )
    if not response.get("success"):
        raise RuntimeError(response.get("msg") or "城市统计报表接口查询失败")
    return _normalize_increase_dash_values(_extract_report_records(response.get("result")))


def _attach_pm25_decimal_increase(
    records: List[Dict[str, Any]],
    *,
    requested_cities: List[str],
    expanded_cities: List[str],
    city_codes: List[str],
    current_range: List[str],
    comparison_range: List[str],
    ns_type: int,
    plan_type: int,
    data_source: int,
    sand_type: int,
    revise_type: int,
    skip_count: int,
    max_result_count: int,
) -> None:
    current_records = _fetch_city_standard_records_for_range(
        requested_cities=requested_cities,
        expanded_cities=expanded_cities,
        city_codes=city_codes,
        time_range=current_range,
        ns_type=ns_type,
        plan_type=plan_type,
        data_source=data_source,
        sand_type=sand_type,
        revise_type=revise_type,
        skip_count=skip_count,
        max_result_count=max_result_count,
    )
    comparison_records = _fetch_city_standard_records_for_range(
        requested_cities=requested_cities,
        expanded_cities=expanded_cities,
        city_codes=city_codes,
        time_range=comparison_range,
        ns_type=ns_type,
        plan_type=plan_type,
        data_source=data_source,
        sand_type=sand_type,
        revise_type=revise_type,
        skip_count=skip_count,
        max_result_count=max_result_count,
    )
    current_by_city = _records_by_city(current_records)
    comparison_by_city = _records_by_city(comparison_records)
    for record in records:
        city_name = _city_name_from_record(record)
        current_record = current_by_city.get(city_name)
        comparison_record = comparison_by_city.get(city_name)
        if not current_record or not comparison_record:
            continue
        increase = _calculate_change_rate(
            _first_present(current_record, "pM2_5_Decimal", "PM2_5_Decimal"),
            _first_present(comparison_record, "pM2_5_Decimal", "PM2_5_Decimal"),
        )
        comparison_decimal = _pm25_reporting_value(comparison_record)
        if comparison_decimal is not None:
            record["pM2_5_Decimal_Compare"] = comparison_decimal
        if increase is not None:
            record["pM2_5_Decimal_Increase"] = increase


async def _execute_split_query_city_standard_report(
    *,
    segments: List[Dict[str, Any]],
    cities: Optional[List[str]],
    pollutant_codes: Optional[List[str]],
    plan_type: int,
    data_source: int,
    sand_type: int,
    revise_type: int,
    skip_count: int,
    max_result_count: int,
    context: Optional[ExecutionContext],
) -> Dict[str, Any]:
    segment_results: List[Dict[str, Any]] = []
    combined_data: List[Dict[str, Any]] = []
    combined_report_file_paths: List[str] = []
    failures: List[str] = []

    for segment in segments:
        result = await execute_query_city_standard_report(
            cities=cities,
            start_time=segment["start_time"],
            end_time=segment["end_time"],
            ns_type=segment["ns_type"],
            pollutant_codes=pollutant_codes,
            plan_type=plan_type,
            data_source=data_source,
            sand_type=sand_type,
            revise_type=revise_type,
            skip_count=skip_count,
            max_result_count=max_result_count,
            context=context,
        )
        if result.get("report_file_path"):
            combined_report_file_paths.append(str(result["report_file_path"]))

        segment_meta = {
            "standard": segment["standard"],
            "ns_type": segment["ns_type"],
            "start_time": segment["start_time"],
            "end_time": segment["end_time"],
            "status": result.get("status"),
            "success": result.get("success"),
            "summary": result.get("summary"),
            "report_file_path": result.get("report_file_path"),
            "data_records": len(result.get("data") or []),
        }
        segment_results.append(segment_meta)

        if not result.get("success"):
            failures.append(result.get("summary") or f"{segment['standard']}分段查询失败")
            continue

        for row in result.get("data") or []:
            if not isinstance(row, dict):
                continue
            combined_row = {
                "标准": segment["standard"],
                "ns_type": segment["ns_type"],
                "查询开始时间": segment["start_time"],
                "查询结束时间": segment["end_time"],
            }
            combined_row.update(row)
            combined_data.append(combined_row)

    success = not failures
    metadata = {
        "schema_version": "v2.0",
        "tool_name": "query_city_standard_report",
        "split_by_standard": True,
        "split_boundary": DEFAULT_NEW_STANDARD_START.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_cities": list(cities or []),
        "plan_type": plan_type,
        "data_source": data_source,
        "sand_type": sand_type,
        "revise_type": revise_type,
        "segments": segment_results,
        "data_records": len(combined_data),
        "data_view": "reporting",
        "data_is_complete_for_requested_scope": success,
        "report_file_paths": combined_report_file_paths,
        "report_note": (
            "跨 2025-01-01 且未显式指定 ns_type 时，工具已按旧国标/新国标拆分查询；"
            "data 合并返回两个分段的请求范围报告口径记录，完整分段报表路径见 metadata.segments。"
        ),
    }
    summary = (
        "城市统计报表跨标准时段查询完成："
        + "；".join(
            f"{item['standard']} {item['start_time']} 至 {item['end_time']} 返回 {item['data_records']} 条 data 记录"
            for item in segment_results
        )
    )
    if failures:
        summary += "；失败分段：" + "；".join(failures)

    return {
        "status": "success" if success and combined_data else ("failed" if failures else "empty"),
        "success": success,
        "data": combined_data,
        "metadata": metadata,
        "summary": summary,
    }


async def execute_query_city_standard_report(
    *,
    cities: Optional[List[str]] = None,
    start_time: str,
    end_time: str,
    ns_type: Optional[int] = None,
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

    ns_type: 2=新国标，1=旧国标；不传且跨 2025-01-01 时自动拆分为旧国标/新国标两段查询。
    """
    start = _normalize_datetime(start_time)
    end = _normalize_datetime(end_time, end_of_day=True)
    default_segments: Optional[List[Dict[str, Any]]] = None
    if ns_type is None:
        default_segments = _build_default_standard_segments(start_time, end_time)
        if not default_segments:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "result": [],
                "metadata": {"tool_name": "query_city_standard_report", "error": "Invalid time range"},
                "summary": "时间范围错误：start_time 不能晚于 end_time",
            }
        if len(default_segments) > 1:
            return await _execute_split_query_city_standard_report(
                segments=default_segments,
                cities=cities,
                pollutant_codes=pollutant_codes,
                plan_type=plan_type,
                data_source=data_source,
                sand_type=sand_type,
                revise_type=revise_type,
                skip_count=skip_count,
                max_result_count=max_result_count,
                context=context,
            )

    ns_type = _resolve_ns_type(ns_type, start_time, end_time)
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

    effective_pollutants = _normalize_pollutant_codes(pollutant_codes)

    payload: Dict[str, Any] = {
        "skipCount": skip_count,
        "maxResultCount": max_result_count,
        "TimeType": 8,
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

    # 判断是否需要传StationCode
    # 1. 包含区域别名 → 不传StationCode（返回全部27条）
    # 2. 包含全部21个城市 → 不传StationCode（返回全部27条）
    # 3. 纯城市查询（非全部） → 传StationCode（只返回指定城市）
    has_region_alias = any(city in REGION_ALIASES for city in requested_cities)
    is_all_cities = set(expanded_cities) == set(ALL_CITIES)

    should_send_station_code = city_codes and not has_region_alias and not is_all_cities

    if should_send_station_code:
        payload["StationCode"] = city_codes

    logger.info(
        "query_city_standard_report_start",
        requested_cities=requested_cities,
        cities=expanded_cities,
        city_codes=city_codes,
        has_region_alias=has_region_alias,
        is_all_cities=is_all_cities,
        should_send_station_code=should_send_station_code,
        ns_type=ns_type,
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

        records = _normalize_increase_dash_values(_extract_report_records(response.get("result")))
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
            "plan_type": plan_type,
            "data_source": data_source,
            "sand_type": sand_type,
            "revise_type": revise_type,
            "total_records": len(records),
            "field_descriptions": get_standard_report_field_descriptions("city"),
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
        reporting_records = build_city_reporting_records(records, expanded_cities or PUBLIC_REPORT_CITY_ORDER)
        report_file_path = save_report_data_package(
            context=context,
            tool_name="query_city_standard_report",
            query={
                "cities": expanded_cities,
                "requested_cities": requested_cities,
                "start_time": start,
                "end_time": end,
                "ns_type": ns_type,
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
            extra_views={"reporting": reporting_records, "raw": records, "result": records},
            package_kind="city_standard_report_api",
        )
        if report_file_path:
            metadata["report_file_path"] = report_file_path
            metadata["result_externalized"] = True
            metadata["default_view"] = "reporting"
            answer_records = _answer_ready_city_records(
                reporting_records,
                expanded_cities=expanded_cities,
                requested_cities=requested_cities,
            )
            metadata["data_records"] = len(answer_records)
            metadata["data_view"] = "reporting"
            metadata["data_is_complete_for_requested_scope"] = True
            result["report_file_path"] = report_file_path
            result["data"] = answer_records
            result.pop("result", None)
            result["summary"] += (
                f" | data 已返回请求范围内完整报告口径记录，"
                f"完整接口报表已保存为 report_file_path: {report_file_path}"
            )

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
        "TimeType": 8,
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

    # 判断是否需要传StationCode
    has_region_alias = any(city in REGION_ALIASES for city in requested_cities)
    is_all_cities = set(expanded_cities) == set(ALL_CITIES)
    should_send_station_code = city_codes and not has_region_alias and not is_all_cities

    if should_send_station_code:
        payload["StationCode"] = city_codes

    logger.info(
        "query_city_standard_yoy_report_start",
        requested_cities=requested_cities,
        cities=expanded_cities,
        city_codes=city_codes,
        has_region_alias=has_region_alias,
        is_all_cities=is_all_cities,
        should_send_station_code=should_send_station_code,
        ns_type=ns_type,
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

        records = _normalize_increase_dash_values(_extract_report_records(response.get("result")))
        pm25_decimal_increase_status = "not_calculated"
        pm25_decimal_increase_error = None
        if records:
            try:
                _attach_pm25_decimal_increase(
                    records,
                    requested_cities=requested_cities,
                    expanded_cities=expanded_cities,
                    city_codes=city_codes,
                    current_range=current_range,
                    comparison_range=comparison_range,
                    ns_type=ns_type,
                    plan_type=plan_type,
                    data_source=data_source,
                    sand_type=sand_type,
                    revise_type=revise_type,
                    skip_count=skip_count,
                    max_result_count=max_result_count,
                )
                pm25_decimal_increase_status = "calculated"
            except Exception as exc:
                pm25_decimal_increase_status = "failed"
                pm25_decimal_increase_error = str(exc)
                logger.warning(
                    "query_city_standard_yoy_pm25_decimal_increase_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
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
            "plan_type": plan_type,
            "data_source": data_source,
            "sand_type": sand_type,
            "revise_type": revise_type,
            "pollutant_codes": effective_pollutants,
            "total_records": len(records),
            "field_descriptions": get_standard_report_field_descriptions("city", comparative=True),
            "request_payload": payload,
            "pm25_decimal_increase": {
                "field": "pM2_5_Decimal_Increase",
                "reporting_label": "PM2.5同比变化率",
                "status": pm25_decimal_increase_status,
                "formula": "(current.pM2_5_Decimal - comparison.pM2_5_Decimal) / comparison.pM2_5_Decimal * 100",
                "precision": "1 decimal",
                "comparison_field": "pM2_5_Decimal_Compare",
                "comparison_reporting_label": "PM2.5对比值",
                "comparison_source": "对比期单时段报表 pM2_5_Decimal；同比接口未直接返回时补充。",
                "standard_note": (
                    "按新标准，PM2.5 使用阶段均值进行统计评价；因此报告视图中的 "
                    "PM2.5对比值 使用 pM2_5_Decimal_Compare，PM2.5同比变化率 使用 "
                    "pM2_5_Decimal_Increase 字段结果。"
                ),
                "error": pm25_decimal_increase_error,
            },
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
        reporting_records = build_city_reporting_records(records, expanded_cities or PUBLIC_REPORT_CITY_ORDER)
        report_file_path = save_report_data_package(
            context=context,
            tool_name="query_city_standard_yoy_report",
            query={
                "cities": expanded_cities,
                "requested_cities": requested_cities,
                "time_point": current_range,
                "contrast_time": comparison_range,
                "ns_type": ns_type,
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
            extra_views={"reporting": reporting_records, "raw": records, "result": records},
            package_kind="city_standard_yoy_report_api",
        )
        if report_file_path:
            metadata["report_file_path"] = report_file_path
            metadata["result_externalized"] = True
            metadata["default_view"] = "reporting"
            answer_records = _answer_ready_city_records(
                reporting_records,
                expanded_cities=expanded_cities,
                requested_cities=requested_cities,
            )
            metadata["data_records"] = len(answer_records)
            metadata["data_view"] = "reporting"
            metadata["data_is_complete_for_requested_scope"] = True
            result["report_file_path"] = report_file_path
            result["data"] = answer_records
            result.pop("result", None)
            result["summary"] += (
                f" | data 已返回请求范围内完整报告口径记录，"
                f"完整接口报表已保存为 report_file_path: {report_file_path}"
            )

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
                "ns_type=2 表示新国标；ns_type=1 表示旧国标；不传时按查询时段自动选择："
                "2025-01-01 之前默认旧国标，2025-01-01 及之后默认新国标；"
                "跨 2025-01-01 时自动拆成旧国标、新国标两次查询并合并返回分段结果。"
                "注意：2025-01-01 之前接口只有旧标准数据，指定 ns_type=2 查询 2025 年前时段通常无数据返回。"
                "工具返回默认使用 reporting 报告口径视图，"
                "其中 PM2.5 已按信息公开规范取 pM2_5_Decimal 并保留1位小数；"
                "cities 传入粤东、粤西、粤北、珠三角、非珠三角、粤东西北、全省/广东省等区域别名时，"
                "接口仍获取含城市和区域的完整报表，但 data 只返回对应区域汇总行，不返回下辖城市明细；"
                "完整城市明细和原始记录保存在 report_file_path 的结构化视图中。"
                "reporting/data 是报告口径精简视图，缺少完整排名明细、单项指数、首要污染物天数/占比、"
                "各等级天数/占比、最大值、小数字段等接口字段；需要这些字段时读取 raw/result/cities 视图。"
                "当 metadata.data_is_complete_for_requested_scope=true 时，data 已是请求范围完整结果，"
                "应直接用 data 作答；"
                "只有需要追溯原始接口字段时才读取 raw/result 视图。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "城市或区域名称列表；可传广东省、全省、珠三角、非珠三角、粤东西北、粤东、粤西、粤北等区域别名。"
                            "传区域别名时 data 只返回对应区域汇总行，不返回下辖城市明细；城市明细可从 registry 的 reporting/raw/result 视图读取。"
                            "不传则由接口返回默认范围。"
                        ),
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
                        "description": (
                            "接口标准类型：2=新国标，1=旧国标；不传时按查询时段自动选择。"
                            "2025-01-01 之前默认旧国标，2025-01-01 及之后默认新国标；"
                            "跨 2025-01-01 时工具自动拆成旧国标、新国标两次查询并合并返回分段结果。"
                            "注意：2025-01-01 之前接口只有旧标准数据，指定 ns_type=2 查询 2025 年前时段通常无数据返回。"
                        ),
                        "enum": [1, 2],
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

        return await execute_query_city_standard_report(
            cities=kwargs.get("cities"),
            start_time=start_time,
            end_time=end_time,
            ns_type=kwargs.get("ns_type"),
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
                "工具返回默认使用 reporting 报告口径视图，"
                "其中 PM2.5 已按信息公开规范取 pM2_5_Decimal 并保留1位小数；"
                "按新标准，PM2.5 使用阶段均值进行统计评价，因此 reporting/data 中的 "
                "PM2.5对比值 使用补算字段 pM2_5_Decimal_Compare，PM2.5同比变化率 "
                "使用补算字段 pM2_5_Decimal_Increase；"
                "接口原始 pM2_5_Compare/pM2_5_Increase 基于修约值，仅作为 "
                "PM2.5接口原始对比值/PM2.5接口原始同比变化率 保留供追溯。"
                "cities 传入粤东、粤西、粤北、珠三角、非珠三角、粤东西北、全省/广东省等区域别名时，"
                "接口仍获取含城市和区域的完整报表，但 data 只返回对应区域汇总行，不返回下辖城市明细；"
                "完整城市明细和原始记录保存在 report_file_path 的结构化视图中。"
                "reporting/data 是报告口径精简视图，缺少完整排名明细、单项指数、首要污染物天数/占比、"
                "各等级天数/占比、最大值、小数字段等接口字段；需要这些字段时读取 raw/result/cities 视图。"
                "当 metadata.data_is_complete_for_requested_scope=true 时，data 已是请求范围完整结果，"
                "应直接用 data 作答；"
                "只有需要追溯原始接口字段时才读取 raw/result 视图。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "城市或区域名称列表；可传广东省、全省、珠三角、非珠三角、粤东西北、粤东、粤西、粤北等区域别名。"
                            "传区域别名时 data 只返回对应区域汇总行，不返回下辖城市明细；城市明细可从 registry 的 reporting/raw/result 视图读取。"
                            "不传则由接口返回默认范围。"
                        ),
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
            pollutant_codes=kwargs.get("pollutant_codes"),
            plan_type=int(kwargs.get("plan_type", 0)),
            data_source=int(kwargs.get("data_source", 1)),
            sand_type=int(kwargs.get("sand_type", 1)),
            revise_type=int(kwargs.get("revise_type", 0)),
            skip_count=int(kwargs.get("skip_count", 0)),
            max_result_count=int(kwargs.get("max_result_count", 200)),
            context=context,
        )
