"""事件审核证据包 → 工单审核工作台的落库适配。

事件流水线（fetcher）按 agent_slim_v1 结构把取证数据写在
``work_order_review_events/<日期>/<事件>/review_evidence_pack.json``，
而工作台（``/api/jiangsu/work-order-reviews``）读的是拆分存储的审核包
（save_evidence：index.json + sources/<name>.json）。两者字段结构不同，
本模块把前者转换成后者并在事件生成时落库，使任务会话右侧的
「工单审核」工作台能直接展示证据包数据，也让 submit_task_review 的
研判回写（attach_judgment）能找到工单条目。

转换失败的来源降级为 skipped/failed，不阻断事件主流程（调用方隔离）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from app.services.jiangsu_work_order_review import save_evidence
from app.tools.jiangsu.review_evidence import (
    POLLUTANT_ROW_KEYS,
    POLLUTANT_UNITS,
    same_city_band,
)

logger = structlog.get_logger()

_VALUE_WITH_FLAG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[（(]([^)）]{1,12})[)）]\s*$")
_MAX_TABLE_ROWS = 200
_MAX_ALARM_ROWS = 50

_SOURCE_ORDER = ("work_order", "station_hour", "band", "weather", "alarms", "env_power", "qc")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tool_payload_rows(payload: Any) -> list[Any]:
    """从工具结果形态的载荷里取记录列表（data 可能为 list 或 {rows...}）。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "returned_records", "tableData"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _flagged_value(value: Any) -> tuple[float | None, str | None]:
    """解析平台数值（可带审核标识，如 "0.984(H)"）→ (数值, 标识)。"""
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    if not text:
        return None, None
    match = _VALUE_WITH_FLAG.match(text)
    if match:
        return float(match.group(1)), match.group(2)
    try:
        return float(text), None
    except ValueError:
        return None, None


def _points_from_rows(rows: list[Any], pollutant: str, *, keep_flags: bool = False) -> list[dict[str, Any]]:
    """宽表原始行 → 图表点序列；无效标识 -99/-999 过滤，保留带标识数值。"""
    keys = POLLUTANT_ROW_KEYS.get(str(pollutant or "").upper(), (pollutant,))
    points: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        time_text = str(row.get("timePoint") or row.get("time") or "").strip()
        if not time_text:
            continue
        for key in keys:
            if key not in row:
                continue
            value, flag = _flagged_value(row.get(key))
            if value is None or value <= -90:
                continue
            point: dict[str, Any] = {"time": time_text, "value": value}
            if keep_flags and flag:
                point["flag"] = flag
            points.append(point)
            break
    points.sort(key=lambda item: item["time"])
    return points


def _detail_record(detail_payload: Any) -> dict[str, Any]:
    """工单详单工具结果 → 单条详单记录（wo/details/workFlowInfo/attachments...）。"""
    for candidate in _tool_payload_rows(detail_payload):
        if isinstance(candidate, dict) and any(
            key in candidate for key in ("wo", "details", "workFlowInfo", "attachments")
        ):
            return candidate
    return {}


def _work_order_source(pack: dict[str, Any]) -> dict[str, Any]:
    work_order = pack.get("work_order") if isinstance(pack.get("work_order"), dict) else {}
    order = work_order.get("list_item") if isinstance(work_order.get("list_item"), dict) else {}
    record = _detail_record(work_order.get("detail"))
    data: dict[str, Any] = {"order": order}
    for key in ("wo", "details", "workFlowInfo", "faultDevice", "changeDevice",
                "faultContentItems", "checkItemList", "attachments"):
        if record.get(key) not in (None, "", [], {}):
            data[key] = record[key]
    data.setdefault("attachments", [])
    if not order and not record:
        return {"status": "skipped", "record_count": 0, "summary": "事件包未含工单详单", "data": data}
    process_count = len(data.get("details") or [])
    attachment_count = len(data.get("attachments") or [])
    summary = f"源平台工单详单（处置过程 {process_count} 条、附件 {attachment_count} 个）" if record else "故障工单清单条目"
    return {"status": "success", "record_count": 1 + process_count, "summary": summary, "data": data}


def _station_hour_source(pack: dict[str, Any], pollutant: str) -> dict[str, Any]:
    monitoring = pack.get("monitoring") if isinstance(pack.get("monitoring"), dict) else {}
    hour_payload = monitoring.get("station_hour_raw")
    rows = _tool_payload_rows(hour_payload)
    points = _points_from_rows(rows, pollutant, keep_flags=True)
    pm25_points = _points_from_rows(rows, "PM2.5") if pollutant != "PM2.5" else []
    if not points:
        return {"status": "empty", "record_count": 0,
                "summary": "小时原始数据未含有效目标污染物数值",
                "data": {"unit": POLLUTANT_UNITS.get(pollutant, "μg/m³"), "pollutant": pollutant,
                         "points": [], "pm25_points": []}}
    return {"status": "success", "record_count": len(points),
            "summary": f"本站 {pollutant} 逐时浓度（含审核标识解析与 PM2.5 对照序列）",
            "data": {"unit": POLLUTANT_UNITS.get(pollutant, "μg/m³"), "pollutant": pollutant,
                     "points": points, "pm25_points": pm25_points}}


def _band_source(pack: dict[str, Any], pollutant: str, station_code: str,
                 event_dir: Path | None) -> dict[str, Any]:
    same_city = pack.get("same_city_monitoring")
    rows: list[Any] = []
    scope = district_name = None
    if isinstance(same_city, dict):
        scope = same_city.get("comparison_scope")
        district_name = same_city.get("district_name")
        rows = _tool_payload_rows(same_city.get("station_hour_raw"))
    if not rows and event_dir is not None:
        raw_path = event_dir / "resources" / "same_city_monitoring_raw.json"
        try:
            import json

            if raw_path.is_file():
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("station_hour_raw"), (dict, list)):
                    payload = payload["station_hour_raw"]
                rows = _tool_payload_rows(payload)
        except (OSError, ValueError) as exc:
            logger.warning("work_order_review_band_raw_read_failed", path=str(raw_path), error=str(exc))
    if not rows:
        return {"status": "skipped", "record_count": 0, "summary": "事件包未含同域对比原始行",
                "data": {"band": []}}
    band = same_city_band(rows, target_station_code=station_code, pollutant=pollutant)
    return {"status": "success" if band else "empty", "record_count": len(band),
            "summary": "同城对比带（本站/最低/中位/最高）",
            "data": {"band": band, "scope": scope, "district_name": district_name}}


def _weather_source(pack: dict[str, Any]) -> dict[str, Any]:
    city_weather = pack.get("city_weather") if isinstance(pack.get("city_weather"), dict) else {}
    rows = city_weather.get("data") if isinstance(city_weather.get("data"), list) else []
    status = str(city_weather.get("status") or ("success" if rows else "unavailable"))
    return {"status": status, "record_count": len(rows),
            "summary": "城市气象时序（风速/风向/温湿压雨）",
            "data": {"rows": rows, "city_name": city_weather.get("city_name"),
                     "gaps": city_weather.get("gaps")}}


def _alarm_row(row: Any) -> dict[str, Any] | None:
    """告警行兼容 dict 与 Python dict-repr 字符串（"@{k=v; k=v}"）两种形态。"""
    if isinstance(row, dict):
        picked = {key: row[key] for key in ("alarmTime", "time", "alarmContent", "description",
                                            "content", "alarmLevel", "alarmGrade", "level",
                                            "alarmName", "alarmType")
                  if row.get(key) is not None}
        return picked or None
    text = str(row or "").strip()
    if not text.startswith("@{"):
        return {"description": text} if text else None
    fields: dict[str, str] = {}
    for chunk in text[2:].rstrip("}").split("; "):
        key, _, value = chunk.partition("=")
        if key:
            fields[key.strip()] = value.strip()
    picked = {key: fields[key] for key in ("alarmTime", "description", "alarmContent",
                                           "alarmGrade", "alarmType") if fields.get(key)}
    return picked or None


def _alarms_source(pack: dict[str, Any]) -> dict[str, Any]:
    payload = pack.get("station_alarm_logs")
    if not isinstance(payload, dict):
        return {"status": "skipped", "record_count": 0, "summary": "事件包未含站房告警",
                "data": {"alarm_logs": []}}
    # data 形态一：[ {station, result: {alarmLogs: [...]}} ]；形态二：data 本身是告警行列表。
    wrapper_rows = _tool_payload_rows(payload)
    raw_rows: list[Any] = []
    for candidate in wrapper_rows:
        if isinstance(candidate, dict) and isinstance(candidate.get("result"), dict):
            raw_rows = candidate["result"].get("alarmLogs") or []
            break
    if not raw_rows and wrapper_rows and not any(
        isinstance(row, dict) and ("result" in row or "station" in row) for row in wrapper_rows
    ):
        raw_rows = wrapper_rows
    logs = [parsed for row in raw_rows[:_MAX_ALARM_ROWS] if (parsed := _alarm_row(row))]
    return {"status": str(payload.get("status") or ("success" if logs else "empty")),
            "record_count": len(logs), "summary": "站房设备告警（当前清单，不按时间窗过滤）",
            "data": {"alarm_logs": logs}}


def _pivot_env_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """动环长表（每行一个要素）→ 宽表（每行一个时刻），匹配工作台列标签。"""
    by_time: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        time_text = str(row.get("timePoint") or row.get("time") or "").strip()
        item = str(row.get("itemCode") or row.get("itemName") or "").strip()
        if not time_text or not item:
            continue
        entry = by_time.get(time_text)
        if entry is None:
            entry = {"timePoint": time_text}
            by_time[time_text] = entry
            order.append(time_text)
        if len(entry) < 40:
            entry[item] = row.get("value")
    return [by_time[time_text] for time_text in order[:_MAX_TABLE_ROWS]]


def _env_power_source(pack: dict[str, Any]) -> dict[str, Any]:
    payload = pack.get("station_environment_history")
    if not isinstance(payload, dict):
        return {"status": "skipped", "record_count": 0,
                "summary": "事件包未含站房动环历史", "data": {"table_rows": []}}
    rows = _tool_payload_rows(payload.get("data"))
    if rows and isinstance(rows[0], dict) and "itemCode" in rows[0]:
        rows = _pivot_env_rows(rows)
    return {"status": str(payload.get("status") or ("success" if rows else "empty")),
            "record_count": len(rows),
            "summary": "站房动环逐时记录（宽表，最多 200 行）",
            "data": {"table_rows": rows}}


def _qc_source(pack: dict[str, Any], pollutant: str) -> dict[str, Any]:
    quality = pack.get("quality_control") if isinstance(pack.get("quality_control"), dict) else {}
    entries = [item for item in _as_list(quality.get("task_details")) if isinstance(item, dict)]
    tasks = []
    for entry in entries:
        task = entry.get("task") if isinstance(entry.get("task"), dict) else {}
        task_pollutant = str(task.get("pollutant") or task.get("poll") or "").strip().upper()
        tasks.append({
            "rId": task.get("r_id") or task.get("rId") or task.get("rid"),
            "poll": task_pollutant or None,
            "qcType": task.get("qc_type") or task.get("qcType"),
            "sStart": task.get("r_start") or task.get("sStart") or task.get("rStart"),
            "qc_result": task.get("qc_result") or task.get("result"),
            "detail": {key: entry[key] for key in ("task", "status", "status_detail",
                                                   "run_log", "curve", "curve_window")
                       if entry.get(key) is not None},
        })
    if pollutant:
        target = [task for task in tasks if task.get("poll") == str(pollutant).upper()]
        if target:
            tasks = target
    if not tasks:
        return {"status": "empty", "record_count": 0,
                "summary": f"时间窗内无{pollutant or '目标污染物'}质控任务",
                "data": {"qc_tasks": []}}
    return {"status": "success", "record_count": len(tasks),
            "summary": f"目标污染物 {pollutant} 质控任务（含合格结果与质控曲线）",
            "data": {"qc_tasks": tasks}}


def build_workbench_package(pack: dict[str, Any], *,
                            event_dir: Path | None = None) -> dict[str, Any] | None:
    """agent_slim_v1 事件证据包 → 工作台拆分存储包（save_evidence 入参）。"""
    if not isinstance(pack, dict):
        return None
    code = str(pack.get("work_order_code") or "").strip()
    if not code:
        return None
    station = pack.get("station") if isinstance(pack.get("station"), dict) else {}
    pollutant_raw = pack.get("pollutants_detected_from_text")
    if isinstance(pollutant_raw, (list, tuple)):
        pollutant = str(next((item for item in pollutant_raw if item), "") or "").strip()
    else:
        pollutant = str(pollutant_raw or "").strip()
    window = pack.get("evidence_time_window") if isinstance(pack.get("evidence_time_window"), dict) else {}
    sources = {
        "work_order": _work_order_source(pack),
        "station_hour": _station_hour_source(pack, pollutant),
        "band": _band_source(pack, pollutant, str(station.get("station_code") or ""), event_dir),
        "weather": _weather_source(pack),
        "alarms": _alarms_source(pack),
        "env_power": _env_power_source(pack),
        "qc": _qc_source(pack, pollutant),
    }
    return {
        "working_order_code": code,
        "title": str(pack.get("summary") or pack.get("title") or code),
        "site_name": station.get("station_name"),
        "site_id": station.get("site_id") or station.get("station_code"),
        "pollutant": pollutant or None,
        "station": station,
        "window": {"start_time": window.get("start"), "end_time": window.get("end")},
        "mark_areas": [],
        "sources": {name: sources[name] for name in _SOURCE_ORDER},
    }


def ingest_event_evidence(pack: dict[str, Any], *, event_dir: Path | str | None = None) -> dict[str, Any] | None:
    """把事件证据包落入工作台存储；返回 manifest 条目，无需落库时返回 None。

    所有异常由调用方隔离（fetcher 里 warning + 继续），不阻断事件生成。
    """
    package = build_workbench_package(pack, event_dir=Path(event_dir) if event_dir else None)
    if package is None:
        return None
    return save_evidence(package)
