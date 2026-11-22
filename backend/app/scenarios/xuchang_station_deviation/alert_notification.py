"""Deterministic station-alert notification for Xuchang Scenario 1.

推送文案由代码从证据包确定性渲染（2026-11-19 起收敛为 6 条目紧凑格式），
不再经 LLM 生成：格式 100% 稳定、告警推送延迟更低。微信群 RPA 对以【开头
的文案不叠加全局前缀，故标题固定为【浓度告警】。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.scheduled_tasks.event_delivery import EventTaskDelivery
from app.scheduled_tasks.event_output import BroadcastPayload, EventTaskOutput
from app.scenarios.xuchang_station_deviation.wechat_push_queue import (
    enqueue_station_alert_wechat_message,
)
from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger()

POLLUTANT_UNITS = {"CO": "毫克/立方米"}
DEFAULT_UNIT = "微克/立方米"

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 16 方位（主方位在前、偏转在后），与推送文案「西北偏西风」口径一致。
WIND_BEARINGS = (
    "北", "东北偏北", "东北", "东北偏东", "东", "东南偏东", "东南", "东南偏南",
    "南", "西南偏南", "西南", "西南偏西", "西", "西北偏西", "西北", "西北偏北",
)


def _wind_bearing(degrees: Any) -> str:
    try:
        value = float(degrees)
    except (TypeError, ValueError):
        return "未知方向"
    return WIND_BEARINGS[int(((value % 360) + 11.25) // 22.5) % 16]


def _unit(pollutant: str) -> str:
    return POLLUTANT_UNITS.get(pollutant, DEFAULT_UNIT)


def _dec(value: Any, digits: int = 1) -> str:
    """定点小数格式化（保留尾零，如 40.0）；缺测/NaN 返回「缺测」。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "缺测"
    if number != number:  # NaN
        return "缺测"
    return f"{number:.{digits}f}"


def _fmt_time_cn(value: Any) -> str:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return str(value or "未知时间")
    if moment.tzinfo is not None:
        moment = moment.astimezone(TZ_SHANGHAI)
    return moment.strftime("%Y年%m月%d日%H:%M")


def _parse_moment(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _station_name(alert: dict[str, Any], override: str | None = None) -> str:
    name = str(override or alert.get("station_name") or alert.get("station_id") or "未知站点")
    if alert.get("is_upgrade"):
        name = f"【升级】{name}"
    elif alert.get("is_renotify"):
        name = f"【持续】{name}"
    return name


def _deviation_fact(alert: dict[str, Any], name: str, unit: str) -> str:
    """站点离群事实句：实测、周边站均值、绝对偏差、相对偏差。"""
    parts = [f"{name}实测{_dec(alert.get('station_value'))}{unit}"]
    peer_mean = alert.get("peer_mean")
    if peer_mean is not None:
        count = _dec(alert.get("peer_station_count"), 0)
        label = f"周边{count}站均值" if count and count != "0" else "周边站均值"
        parts.append(f"{label}{_dec(peer_mean)}")
    if alert.get("absolute_delta") is not None:
        parts.append(f"绝对偏差{_dec(alert.get('absolute_delta'))}")
    if alert.get("deviation_percent") is not None:
        parts.append(f"相对偏差{_dec(alert.get('deviation_percent'))}%")
    return "，".join(parts)


def _rise_fact(alert: dict[str, Any], name: str, unit: str) -> str:
    """连续抬升事实句：实测、窗口抬升过程、累计抬升。"""
    parts = [f"{name}实测{_dec(alert.get('station_value'))}{unit}"]
    window = alert.get("rise_window_values") or []
    if window:
        if str(alert.get("measurement_granularity")) == "hour":
            count = alert.get("rise_count") or len(window) - 1
            parts.append(
                f"从{_dec(window[0])}连续{count}个小时节抬升至{_dec(window[-1])}"
            )
        else:
            parts.append(
                f"30分钟内从{_dec(window[0])}连续6个5分钟节抬升至{_dec(window[-1])}"
            )
    total_abs = alert.get("total_rise_abs")
    if total_abs is not None:
        sentence = f"累计抬升{_dec(total_abs)}"
        total_rate = alert.get("total_rise_rate")
        if total_rate is not None:
            sentence += f"（累计涨幅{_dec(float(total_rate) * 100)}%）"
        parts.append(sentence)
    return "，".join(parts)


def _sudden_fact(alert: dict[str, Any], name: str, unit: str) -> str:
    """单点突升事实句：实测、较近段基线抬升、触发阈值。"""
    detail = alert.get("detail") or {}
    parts = [f"{name}实测{_dec(alert.get('station_value'))}{unit}"]
    if detail.get("baseline") is not None:
        parts.append(f"较近段基线{_dec(detail.get('baseline'))}抬升{_dec(detail.get('delta'))}")
    if detail.get("threshold") is not None:
        parts.append(f"达到触发阈值{_dec(detail.get('threshold'))}")
    return "，".join(parts)


def _limit_fact(alert: dict[str, Any], name: str, unit: str) -> str:
    """限值突破事实句：实测、分档限值与触发口径。"""
    detail = alert.get("detail") or {}
    parts = [f"{name}实测{_dec(alert.get('station_value'))}{unit}"]
    threshold = detail.get("limit_threshold")
    if threshold is not None:
        bin_name = detail.get("limit_bin") or ""
        version = detail.get("limit_version") or "现行限值"
        parts.append(f"超{bin_name}档限值{_dec(threshold)}（{version}）")
    trigger = detail.get("trigger")
    if trigger:
        parts.append(str(trigger))
    return "，".join(parts)


def _multi_station_fact(alert: dict[str, Any], name: str, unit: str) -> str:
    """多站同步抬升事实句：主站事实 + 路径与覆盖说明（其余站由区域清单句渲染）。"""
    detail = alert.get("detail") or {}
    involved = detail.get("involved_stations") or []
    path = str(detail.get("path") or "co_rise")
    primary = next(
        (item for item in involved if str(item.get("station_id")) == str(alert.get("station_id"))),
        None,
    )
    parts = [f"{name}实测{_dec(alert.get('station_value'))}{unit}"]
    if primary is not None:
        if path == "co_rise" and primary.get("baseline") is not None:
            parts.append(f"较基线{_dec(primary.get('baseline'))}抬升{_dec(primary.get('rise'))}")
        elif primary.get("peer_mean") is not None:
            parts.append(f"周边站均值{_dec(primary.get('peer_mean'))}，偏高{_dec(primary.get('delta'))}")
    parts.append(f"共{len(involved)}站{'同步抬升' if path == 'co_rise' else '一致偏高'}")
    parts.append("已覆盖涉事站点单站告警")
    return "，".join(parts)


def _alert_fact_sentence(alert: dict[str, Any]) -> str:
    """按 rule 类型选择事实句式；区域合并站清单由调用方另行追加。"""
    rule_type = str(alert.get("rule_type") or "")
    rule = str(alert.get("rule") or "")
    unit = _unit(str(alert.get("target_pollutant")))
    name = _station_name(alert)
    if rule_type == "multi_station_rise":
        return _multi_station_fact(alert, name, unit)
    if rule_type == "continuous_rise" or rule.startswith("six_consecutive"):
        return _rise_fact(alert, name, unit)
    if rule_type == "sudden_rise":
        return _sudden_fact(alert, name, unit)
    if rule_type == "limit_breach":
        return _limit_fact(alert, name, unit)
    return _deviation_fact(alert, name, unit)


def _region_station_facts(alert: dict[str, Any]) -> list[str]:
    """区域合并站逐站事实句（DS 合并站带基线抬升信息，CL 仅带实测值）。"""
    stations = (alert.get("detail") or {}).get("region_stations") or []
    unit = _unit(str(alert.get("target_pollutant")))
    facts: list[str] = []
    for item in stations:
        name = str(item.get("station_name") or item.get("station_id") or "未知站点")
        parts = [f"{name}实测{_dec(item.get('station_value'))}{unit}"]
        if item.get("baseline") is not None:
            rise = item.get("rise") if "rise" in item else item.get("delta")
            parts.append(f"较近段基线{_dec(item.get('baseline'))}抬升{_dec(rise)}")
        facts.append("，".join(parts))
    return facts


def _meteorology_clause(evidence: dict[str, Any], occurred_at: str) -> str:
    """取告警时刻前最近一条气象整点观测，缺测项省略。"""
    weather = evidence.get("observed_meteorology") or {}
    if weather.get("status") != "success":
        return "暂无可用气象观测"
    records = weather.get("station_hour_records") or []
    reference = _parse_moment(occurred_at)
    candidates = [
        (moment, record)
        for record in records
        if (moment := _parse_moment(record.get("time"))) is not None
        and (reference is None or moment <= reference)
    ]
    if not candidates:
        return "暂无可用气象观测"
    _, latest = max(candidates, key=lambda item: item[0])
    parts: list[str] = []
    if latest.get("temperature_2m") is not None:
        parts.append(f"温度{_dec(latest.get('temperature_2m'))}℃")
    if latest.get("relative_humidity_2m") is not None:
        parts.append(f"相对湿度{_dec(latest.get('relative_humidity_2m'), 0)}%")
    if latest.get("wind_direction_10m") is not None:
        parts.append(f"{_wind_bearing(latest.get('wind_direction_10m'))}风")
    if latest.get("wind_speed_10m") is not None:
        parts.append(f"风速{_dec(latest.get('wind_speed_10m'))}米/秒")
    return "，".join(parts) if parts else "暂无可用气象观测"


def _qc_clause(evidence: dict[str, Any]) -> str:
    context = evidence.get("air_quality_context") or {}
    qc = evidence.get("maintenance_qc_review") or context.get("maintenance_qc_review")
    if qc:
        marked = qc.get("records") or []
        if marked:
            return (
                f"前一小时内存在{len(marked)}条质控标记记录，"
                "相关时段数据受运维质控影响，须与污染事实区分"
            )
        return "存在质控标记记录，相关时段数据受运维质控影响，须与污染事实区分"
    indicators = evidence.get("computed_indicators") or {}
    process = indicators.get("station_5min_process") or {}
    records = process.get("marked_quality_records") or []
    if records:
        return (
            f"前一小时内存在{len(records)}条带质控标记的监测记录，"
            "标记时段不作为污染异常事实直接解释"
        )
    return "前一小时内无质控记录"


def compose_station_alert_message(package: dict[str, Any]) -> str:
    """从证据包确定性渲染 6 条目紧凑通报（微信 RPA/App 广播共用一份文案）。"""
    alerts = package.get("alerts") or []
    if not alerts:
        raise RuntimeError("证据包不含告警因子，无法生成通报")
    primary = alerts[0].get("alert") or {}
    first_evidence = alerts[0].get("evidence") or {}
    occurred_at = str(primary.get("occurred_at") or package.get("occurred_at") or "")

    primary_name = str(primary.get("station_name") or primary.get("station_id") or "未知站点")
    station_names = [primary_name]
    for item in alerts:
        detail = (item.get("alert") or {}).get("detail") or {}
        for entry in detail.get("region_stations") or []:
            name = str(entry.get("station_name") or entry.get("station_id") or "").strip()
            if name and name not in station_names:
                station_names.append(name)

    pollutants: list[str] = []
    for item in alerts:
        pollutant = str((item.get("alert") or {}).get("target_pollutant") or "").strip()
        if pollutant and pollutant not in pollutants:
            pollutants.append(pollutant)
    pollutant_line = "、".join(pollutants) or "未知因子"
    if str(primary.get("measurement_granularity")) == "hour":
        pollutant_line += "（小时数据）"

    facts: list[str] = []
    for item in alerts:
        alert = item.get("alert") or {}
        facts.append(_alert_fact_sentence(alert))
        facts.extend(_region_station_facts(alert))

    lines = [
        f"【浓度告警】1.告警站点：{'，'.join(station_names)}",
        f"2.告警时间：{_fmt_time_cn(occurred_at)}",
        f"3.污染指标：{pollutant_line}",
        f"4.告警情况：{'；'.join(facts)}",
        f"5.气象情况：{_meteorology_clause(first_evidence, occurred_at)}",
        f"6.质控关联：{_qc_clause(first_evidence)}",
    ]
    return "\n".join(lines)


def compose_station_alert_fallback_message(package: dict[str, Any]) -> str:
    """兼容旧调用点：文案已收敛为单一确定性渲染器。"""
    return compose_station_alert_message(package)


def _collect_media(package: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for source in [package.get("dispatch_media") or []] + [
        (item.get("alert") or {}).get("dispatch_media")
        or (item.get("evidence") or {}).get("dispatch_media")
        or []
        for item in package.get("alerts") or []
    ]:
        for path in source:
            if path and path not in paths:
                paths.append(str(path))
    existing: list[str] = []
    for path in paths:
        try:
            if resolve_agent_path(path).is_file():
                existing.append(path)
        except (ValueError, OSError):
            continue
    return existing


def _load_package(path_value: str) -> dict[str, Any]:
    path = resolve_agent_path(path_value)
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def run_station_alert_workflow(
    *,
    task: Any,
    execution: Any,
    event: Any,
    history_section: str | None = None,
) -> dict[str, Any]:
    """Read the episode evidence package, render the notice and broadcast it."""
    payload = (event.payload if event is not None else {}) or {}
    package_path = str(payload.get("evidence_package_path") or "").strip()
    if not package_path:
        raise RuntimeError("事件 payload 缺少 evidence_package_path，工作流无法执行")

    package = await asyncio.to_thread(_load_package, package_path)
    message = compose_station_alert_message(package)
    media = await asyncio.to_thread(_collect_media, package)

    # 微信群 RPA 推送：文案定稿即入队（含证据附图路径），先于现有投递；
    # 失败不影响 App/GeTui 主流程
    try:
        enqueued = enqueue_station_alert_wechat_message(
            package, message, media=media
        )
        if enqueued:
            logger.info("xuchang_wechat_push_enqueued", message_id=enqueued["id"])
    except Exception:
        logger.warning("xuchang_wechat_push_enqueue_failed", exc_info=True)

    output = EventTaskOutput(
        success=True,
        broadcast=BroadcastPayload(message=message, media=media),
    )
    delivery = EventTaskDelivery()
    recipients = await delivery.resolve_recipients(list(task.target_user_ids or []))
    if not recipients:
        raise RuntimeError("无可用社交接收对象，告警通报未投递")
    delivery_results = await delivery.deliver(
        task=task,
        event=event,
        execution=execution,
        output=output,
        recipients=recipients,
    )
    sent_count = sum(1 for row in delivery_results if row.get("sent"))
    pollutants = "、".join(
        str((item.get("alert") or {}).get("target_pollutant") or "未知因子")
        for item in package.get("alerts") or []
    )
    summary = (
        f"站点快速告警通报已生成并投递：{package.get('station_id', '')} "
        f"{package.get('station_name', '')}（{pollutants}），"
        f"接收对象{len(recipients)}个，投递成功{sent_count}个，附图{len(media)}张。"
    )
    if sent_count < len(recipients):
        raise RuntimeError(f"部分接收对象投递失败（{sent_count}/{len(recipients)}）")
    return {
        "summary": summary,
        "final_message": message,
        "data_ids": [],
        "tool_call_details": {
            "recipients": [row.get("user_id") for row in delivery_results],
            "media_count": len(media),
            "media": media,
            "evidence_package_path": package_path,
        },
    }
