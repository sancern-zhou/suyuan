from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import structlog

from app.agent.context.execution_context import ExecutionContext
from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger()


CITY_FIELD_ALIASES = ("city", "cityName", "areaName", "AreaName", "城市", "地市", "name")

FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "AQI达标率": (
        "fineRate",
        "FineRate",
        "AQIStandardRate",
        "aqi_standard_rate",
        "aqi_rate",
        "AQI达标率",
        "达标率",
        "优良率",
    ),
    "PM2.5": (
        "pM2_5_Decimal",
        "PM2_5_Decimal",
    ),
    "PM10": ("pM10", "PM10", "pm10", "PM10浓度"),
    "O3": ("o3_8h", "O3_8h", "O3-8h", "o3", "O3", "臭氧", "臭氧(O3)", "O3浓度", "O3评价浓度"),
    "NO2": ("nO2", "NO2", "no2", "二氧化氮", "NO2浓度"),
}

FIELD_POLICY = {
    "PM2.5": "PM2.5只能使用阶段均值字段pM2_5_Decimal。",
    "PM10": "PM10只能使用修约均值字段pM10。",
    "O3": "O3只能使用修约均值字段o3_8h。",
    "NO2": "NO2只能使用修约均值字段nO2。",
}

POLLUTANT_LABELS = {
    "PM2_5": "PM2.5",
    "PM25": "PM2.5",
    "PM2.5": "PM2.5",
    "PM10": "PM10",
    "O3": "O3",
    "O3_8H": "O3",
    "O3_8h": "O3",
}

SECONDARY_ORDER = ("AQI达标率", "PM2.5", "O3", "NO2", "PM10")

GUANGDONG_CITY_NAMES = {
    "广州",
    "深圳",
    "珠海",
    "汕头",
    "佛山",
    "韶关",
    "河源",
    "梅州",
    "惠州",
    "汕尾",
    "东莞",
    "中山",
    "江门",
    "阳江",
    "湛江",
    "茂名",
    "肇庆",
    "清远",
    "潮州",
    "揭阳",
    "云浮",
}


def build_city_pollutant_rankings(
    records: Sequence[Dict[str, Any]],
    *,
    pollutants: Optional[Sequence[str]] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Build deterministic city pollutant low/high rankings."""
    if not records:
        raise ValueError("records 不能为空")

    requested_pollutants = [_normalize_pollutant_name(p) for p in (pollutants or ("PM2.5", "PM10", "O3"))]
    top_n = int(top_n or 5)
    if top_n <= 0:
        raise ValueError("top_n 必须大于0")

    normalized_records = _filter_city_rows([_normalize_record(record) for record in records])
    rankings: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    ranking_keys: Dict[str, List[Dict[str, str]]] = {}
    air_quality_keys = ["AQI达标率", "PM2.5", "O3", "NO2", "城市"]
    required_keys = list(air_quality_keys)
    for pollutant in requested_pollutants:
        for key in _ranking_keys_for_pollutant(pollutant):
            if key not in required_keys:
                required_keys.append(key)
    _validate_required_values(normalized_records, required_keys)

    air_quality_good = sorted(normalized_records, key=lambda row: _air_quality_sort_key(row, poor=False))
    air_quality_poor = sorted(normalized_records, key=lambda row: _air_quality_sort_key(row, poor=True))

    for pollutant in requested_pollutants:
        keys = _ranking_keys_for_pollutant(pollutant)
        ranking_keys[pollutant] = [{"field": key, "label": key} for key in keys]

        low_sorted = sorted(normalized_records, key=lambda row: _sort_key(row, keys, high=False))
        high_sorted = sorted(normalized_records, key=lambda row: _sort_key(row, keys, high=True))

        rankings[pollutant] = {
            "low": [_result_row(row, pollutant, keys, rank) for rank, row in enumerate(low_sorted[:top_n], 1)],
            "high": [_result_row(row, pollutant, keys, rank) for rank, row in enumerate(high_sorted[:top_n], 1)],
        }

    return {
        "air_quality": {
            "good": [_air_quality_result_row(row, rank) for rank, row in enumerate(air_quality_good[:top_n], 1)],
            "poor": [_air_quality_result_row(row, rank) for rank, row in enumerate(air_quality_poor[:top_n], 1)],
        },
        "air_quality_ranking_keys": [{"field": key, "label": key} for key in air_quality_keys],
        "rankings": rankings,
        "ranking_keys": ranking_keys,
        "record_count": len(normalized_records),
        "top_n": top_n,
        "field_policy": FIELD_POLICY,
        "rule_note": (
            "空气质量较好排名按AQI达标率从高到低，并列时按PM2.5、O3、NO2浓度低排序；"
            "空气质量较差排名按AQI达标率从低到高，并列时按PM2.5、O3、NO2浓度高排序。"
            "较低排名按主污染物浓度从低到高，并列时按AQI达标率高、其他污染物浓度低排序；"
            "较高排名按主污染物浓度从高到低，并列时按AQI达标率低、其他污染物浓度高排序；"
            "主污染物对应的次指标会跳过，最后按城市名稳定排序。"
            "字段口径：PM2.5只能使用阶段均值，其他污染物指标只能使用修约均值。"
        ),
    }


def _normalize_pollutant_name(value: str) -> str:
    cleaned = str(value or "").strip()
    key = cleaned.upper().replace(" ", "").replace("_", "")
    if key in {"PM25", "PM2.5", "PM2_5".replace("_", "")}:
        return "PM2.5"
    if key == "PM10":
        return "PM10"
    if key in {"O3", "O38H"} or cleaned in {"臭氧", "臭氧(O3)", "O3评价浓度"}:
        return "O3"
    raise ValueError(f"不支持的污染物: {value}")


def _ranking_keys_for_pollutant(pollutant: str) -> List[str]:
    keys = [pollutant]
    keys.extend(key for key in SECONDARY_ORDER if key != pollutant)
    keys.append("城市")
    return keys


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "source": record,
        "城市": _first_present(record, CITY_FIELD_ALIASES),
    }
    if not row["城市"]:
        row["城市"] = _first_present(record, ("city_code", "cityCode", "AreaCode")) or ""
    row["城市"] = str(row["城市"]).strip()

    for canonical, aliases in FIELD_ALIASES.items():
        row[canonical] = _to_number(_first_present(record, aliases))

    return row


def _filter_city_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    guangdong_city_rows = [row for row in records if _city_base_name(row.get("城市")) in GUANGDONG_CITY_NAMES]
    if guangdong_city_rows:
        return guangdong_city_rows
    return records


def _city_base_name(city: Any) -> str:
    text = str(city or "").strip()
    return text[:-1] if text.endswith("市") else text


def _first_present(record: Dict[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", "")
    if text in {"", "—", "-", "无", "None", "null", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _validate_required_values(records: Sequence[Dict[str, Any]], keys: Sequence[str]) -> None:
    missing: Dict[str, List[str]] = {}
    value_keys = [key for key in keys if key != "城市"]
    for row in records:
        city = row.get("城市") or "<未命名城市>"
        for key in value_keys:
            if row.get(key) is None:
                missing.setdefault(key, []).append(city)
    if missing:
        detail = "; ".join(f"{field}: {', '.join(cities[:5])}" for field, cities in missing.items())
        raise ValueError(f"排名所需字段缺失或非数值: {detail}")


def _sort_key(row: Dict[str, Any], keys: Sequence[str], *, high: bool) -> Tuple[Any, ...]:
    sort_parts: List[Any] = []
    for index, key in enumerate(keys):
        if key == "城市":
            sort_parts.append(str(row.get("城市") or ""))
            continue
        value = row.get(key)
        if value is None:
            sort_parts.append(float("inf"))
            continue
        if index == 0:
            sort_parts.append(-value if high else value)
        elif key == "AQI达标率":
            sort_parts.append(value if high else -value)
        else:
            sort_parts.append(-value if high else value)
    return tuple(sort_parts)


def _air_quality_sort_key(row: Dict[str, Any], *, poor: bool) -> Tuple[Any, ...]:
    values = {
        "AQI达标率": row.get("AQI达标率"),
        "PM2.5": row.get("PM2.5"),
        "O3": row.get("O3"),
        "NO2": row.get("NO2"),
    }
    if poor:
        return (
            values["AQI达标率"],
            -values["PM2.5"],
            -values["O3"],
            -values["NO2"],
            str(row.get("城市") or ""),
        )
    return (
        -values["AQI达标率"],
        values["PM2.5"],
        values["O3"],
        values["NO2"],
        str(row.get("城市") or ""),
    )


def _result_row(row: Dict[str, Any], pollutant: str, keys: Sequence[str], rank: int) -> Dict[str, Any]:
    return {
        "rank": rank,
        "city": row["城市"],
        "pollutant": pollutant,
        "concentration": row[pollutant],
        "tie_break_values": {key: row[key] for key in keys[1:] if key != "城市"},
        "sort_values": {key: row[key] for key in keys if key != "城市"},
    }


def _air_quality_result_row(row: Dict[str, Any], rank: int) -> Dict[str, Any]:
    return {
        "rank": rank,
        "city": row["城市"],
        "aqi_standard_rate": row["AQI达标率"],
        "tie_break_values": {
            "PM2.5": row["PM2.5"],
            "O3": row["O3"],
            "NO2": row["NO2"],
        },
        "sort_values": {
            "AQI达标率": row["AQI达标率"],
            "PM2.5": row["PM2.5"],
            "O3": row["O3"],
            "NO2": row["NO2"],
        },
    }


def _records_from_file_path(
    context: ExecutionContext,
    file_path: str,
    preferred_view: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    payload = context.get_data_payload(file_path)
    if isinstance(payload, list):
        return payload, "dataset"
    if not isinstance(payload, dict):
        raise ValueError(f"file_path 数据格式不支持: {type(payload).__name__}")

    views = payload.get("views")
    if isinstance(views, dict):
        candidate_views = [preferred_view] if preferred_view else []
        candidate_views.extend(["cities", "raw", "result", "reporting"])
        for view in candidate_views:
            if view and isinstance(views.get(view), list):
                return views[view], view
        raise ValueError(f"报表数据包没有可用于城市排名的列表视图，可用视图: {', '.join(views.keys())}")

    for key in ("data", "result", "records"):
        if isinstance(payload.get(key), list):
            return payload[key], key
    raise ValueError("对象型数据中未找到可排名的记录列表")

class CityPollutantRankingsTool(LLMTool):
    """Deterministic city pollutant ranking tool for report mode."""

    def __init__(self) -> None:
        function_schema = {
            "name": "analyze_city_pollutant_rankings",
            "description": (
                "确定性城市排名分析工具。用于空气质量通报中空气质量较好/较差各5市，以及 "
                "PM2.5、PM10、O3 浓度较低/较高各5市排名。一次调用可完成空气质量和多个污染物排名。"
                "优先传 query_city_standard_report/query_city_standard_yoy_report 返回的 report_file_path；"
                "工具会优先读取 cities/raw/result/reporting 视图并按固定并列规则排序，避免模型手工排序错误。"
                "字段口径：PM2.5只能使用阶段均值pM2_5_Decimal；PM10、O3、NO2等其他污染物指标"
                "只能使用修约均值pM10、o3_8h、nO2，缺少这些字段时直接失败。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "统计报表的会话文件路径（通常为上游工具返回的 report_file_path）。",
                    },
                    "view": {
                        "type": "string",
                        "description": "可选，指定读取报表包视图，如 cities、raw、result、reporting。不传默认优先读取 cities。",
                    },
                    "records": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "可选，直接传城市统计记录。通常不建议大批量直接传，优先用 file_path。",
                    },
                    "pollutants": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["PM2.5", "PM10", "O3"]},
                        "description": "要排名的污染物，默认一次完成 PM2.5、PM10、O3。",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "每类排名返回城市数，默认5。",
                        "default": 5,
                    },
                },
                "anyOf": [{"required": ["file_path"]}, {"required": ["records"]}],
            },
        }
        super().__init__(
            name="analyze_city_pollutant_rankings",
            description="Analyze city pollutant low/high rankings deterministically",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional[ExecutionContext] = None,
        file_path: Optional[str] = None,
        view: Optional[str] = None,
        records: Optional[List[Dict[str, Any]]] = None,
        pollutants: Optional[List[str]] = None,
        top_n: int = 5,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            source = "records"
            if records is None:
                if not file_path:
                    return {
                        "status": "failed",
                        "success": False,
                        "data": {},
                        "metadata": {"tool_name": self.name, "error": "missing_data_source"},
                        "summary": "缺少 records 或 file_path，无法进行排名分析。",
                    }
                if context is None:
                    raise ValueError("读取 file_path 需要执行上下文")
                records, source = _records_from_file_path(context, file_path, view)

            result = build_city_pollutant_rankings(records, pollutants=pollutants, top_n=top_n)
            metadata = {
                "tool_name": self.name,
                "source": source,
                "input_file_path": file_path,
                "pollutants": list(result["rankings"].keys()),
                "top_n": result["top_n"],
            }
            output_file_path = None
            try:
                if context is None:
                    raise ValueError("保存排名结果需要执行上下文")
                output_file_path = context.save_data(
                    data={"metadata": metadata, **result},
                    schema="city_pollutant_rankings",
                    metadata={**metadata, "session_id": context.session_id if context else None},
                )
                metadata["file_path"] = output_file_path
            except Exception as exc:
                logger.warning("city_pollutant_rankings_save_failed", error=str(exc))

            summary = (
                f"已完成空气质量较好/较差及{', '.join(result['rankings'].keys())}城市污染物较低/较高排名分析，"
                f"每类返回前{result['top_n']}市。"
            )
            if output_file_path:
                summary += f" 排名结果已保存为 file_path: {output_file_path}"

            return {
                "status": "success",
                "success": True,
                "data": result,
                "file_path": output_file_path,
                "metadata": metadata,
                "summary": summary,
            }
        except Exception as exc:
            logger.error("city_pollutant_rankings_failed", error=str(exc), error_type=type(exc).__name__)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {"tool_name": self.name, "error": str(exc)},
                "summary": f"城市污染物排名分析失败：{exc}",
            }
