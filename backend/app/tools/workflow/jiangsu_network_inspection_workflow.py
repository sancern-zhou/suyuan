"""江苏全网巡检汇总工作流。

工作流只负责固定口径的数据汇总和短结论生成；复杂解释仍交给 Agent。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from .workflow_tool import WorkflowTool
from app.tools.jiangsu.fault_diagnosis import JiangsuNetworkInspectionSummaryTool


_PERIOD_LABELS = {"day": "昨日", "week": "最近一周", "month": "本月"}
_MAX_CONCLUSION_CHARS = 300
_MIN_CONCLUSION_CHARS = 200


def _first(item: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _is_alarm(item: Dict[str, Any]) -> bool:
    value = item.get("IsAlarm", item.get("isAlarm", item.get("alarm")))
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "是"}


def build_network_inspection_result(result: Dict[str, Any], period: str) -> Dict[str, Any]:
    """从接口结果生成稳定的统计结果和 200-300 字短结论。"""
    stations = result.get("staList") or result.get("stationList") or []
    alarms = result.get("alarmInfo") or []
    stations = [item for item in stations if isinstance(item, dict)]
    alarms = [item for item in alarms if isinstance(item, dict)]
    alarm_stations = [item for item in stations if _is_alarm(item)]

    # The live endpoint keeps the alarm category in alarmInfo rather than on
    # each staList row. Build a code lookup so the issue list and statistics
    # retain that information without changing the source tool contract.
    alarm_category_by_code: Dict[str, str] = {}
    for group in alarms:
        group_name = _first(group, "name", "Name", default="巡检异常")
        for alarm in group.get("list") or []:
            if not isinstance(alarm, dict):
                continue
            code = _first(alarm, "code", "Code", "stationCode", "StationCode")
            if code:
                alarm_category_by_code[code] = group_name

    city_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    issues: List[Dict[str, Any]] = []
    for item in alarm_stations:
        city = _first(item, "CityName", "cityName", "city", default="未知城市")
        city_counter[city] += 1
        category = _first(
            item,
            "AlarmTypeName",
            "alarmTypeName",
            "AlarmType",
            "alarmType",
            "CategoryName",
            "categoryName",
            default=alarm_category_by_code.get(
                _first(item, "StationCode", "stationCode", "code", "Code", "UniqueCode", "uniqueCode"),
                "巡检异常",
            ),
        )
        category_counter[category] += 1
        if len(issues) < 20:
            issues.append(
                {
                    "station_name": _first(
                        item, "StationName", "stationName", "name", "Name", "PositionName", "positionName", default="未命名站点"
                    ),
                    "station_code": _first(item, "StationCode", "stationCode", "code", "Code", "UniqueCode", "uniqueCode"),
                    "city": city,
                    "category": category,
                    "raw": item,
                }
            )

    top_cities = sorted(city_counter.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
    top_categories = sorted(category_counter.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
    period_label = _PERIOD_LABELS.get(period, period)
    city_text = "、".join(f"{city}{count}站" for city, count in top_cities) or "暂无异常城市"
    category_text = "、".join(f"{name}{count}项" for name, count in top_categories) or "暂无异常类别"

    conclusion = (
        f"{period_label}全网巡检覆盖{len(stations)}个站点，其中{len(alarm_stations)}个站点存在异常，"
        f"涉及{len(city_counter)}个城市。异常站点主要集中在{city_text}；异常类别以{category_text}为主。"
        "建议优先核查异常数量较多的城市和持续出现的站点，结合站房环境、采样系统、动环及历史工单进一步确认。"
        "本结论仅依据自动巡检汇总接口，未代表已完成现场核查；接口无记录或字段缺失的站点应标记为待确认。"
    )
    # 固定短结论上限；数据较少时补充边界说明，确保可直接作为值班摘要使用。
    while len(conclusion) < _MIN_CONCLUSION_CHARS:
        conclusion += "后续处置需由运维人员人工确认，并以现场核查结果为准。"
    conclusion = conclusion[:_MAX_CONCLUSION_CHARS]
    return {
        "period": period,
        "period_label": period_label,
        "station_count": len(stations),
        "alarm_station_count": len(alarm_stations),
        "alarm_city_count": len(city_counter),
        "city_statistics": [{"city": city, "count": count} for city, count in top_cities],
        "category_statistics": [{"category": name, "count": count} for name, count in top_categories],
        "issues": issues,
        "conclusion": conclusion,
        "conclusion_char_count": len(conclusion),
    }


class JiangsuNetworkInspectionWorkflow(WorkflowTool):
    """固定周期的江苏全网巡检短结论工作流。"""

    name = "jiangsu_network_inspection_workflow"
    description = "按日、周或月读取江苏全网巡检汇总，输出异常统计、问题清单和 200-300 字短结论；不生成完整报告、不执行写操作。"
    version = "1.0.0"
    category = "jiangsu_network_inspection"
    requires_context = True

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                        "default": "day",
                        "description": "统计周期：day 昨日、week 最近一周、month 本月。",
                    }
                },
                "required": [],
            },
        }

    async def execute(self, context=None, period: str = "day", **_: Any) -> Dict[str, Any]:
        self._start_timer()
        period = str(period or "day").strip().lower()
        if period not in _PERIOD_LABELS:
            return self._build_udf_v2_result("failed", False, {"period": period}, summary="巡检汇总失败：period 必须是 day、week 或 month")
        self._record_step("fetch_network_inspection_summary", "running", {"period": period})
        raw = await JiangsuNetworkInspectionSummaryTool().execute(context=context, period=period)
        if not raw.get("success"):
            self._record_step("fetch_network_inspection_summary", "failed")
            return self._build_udf_v2_result("failed", False, raw.get("data") or {}, summary=raw.get("summary", "全网巡检汇总失败"))
        self._record_step("fetch_network_inspection_summary", "success", raw.get("metadata") or {})
        data = build_network_inspection_result(raw.get("data") or {}, period)
        self._record_step("deterministic_aggregation", "success", {"issue_count": len(data["issues"])})
        return self._build_udf_v2_result(
            "success",
            True,
            data,
            summary=data["conclusion"],
            extra_metadata={"source": raw.get("metadata", {}), "output_type": "short_conclusion_and_issue_list"},
        )
