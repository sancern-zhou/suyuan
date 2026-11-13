"""浓度告警规则引擎（判据修订版）。

实现《空气质量浓度数据告警规则体系（判据修订）》规则总表：

- 单点突升 DS：当前值 − 基线 >= MAX(基线 × 比例, 绝对增量)；单窗口成立，
  前提是邻站未同向；
- 连续抬升 CL：3 段单调不减，每段增量 >= 总增量 15%，累计抬升达到阈值；
  基线取抬升起点前 15 分钟均值（PM2.5 取起点前一小时）；
- 站点离群 OL：本站与同区域其余有效站同刻平均值比较，达到比例 + 绝对
  增量阈值；许昌全市 6 个国控站，有效站最少 4 个。

O3 暂不纳入；限值突破（R1）不保留；不再输出告警级别。每条告警只带
规则类型、当前污染等级和规则优先级（DS > CL > OL）。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_city_exceedance.aqi import aqi_level, iaqi
from app.scenarios.xuchang_station_deviation.rule_config import (
    AirAlertRuleConfig,
    FIVE_MIN_POLLUTANTS,
    LEVEL_CODES,
    LEVEL_NAMES,
    POLLUTANTS,
    RULE_LABELS,
    RULE_PRIORITY,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 与 service.EVENT_TYPE 保持同一取值（事件由同一条工作流链路消费）。
EVENT_TYPE = "xuchang.station_deviation.alert_created"

GRANULARITY_5MIN = "5min"
GRANULARITY_HOUR = "hour"

POLLUTANT_COLUMNS = {
    "PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "CO": "co",
}
OBSERVED_INDICATORS = {"PM2.5": "PM2.5", "PM10": "PM10", "SO2": "SO2", "NO2": "NO2", "CO": "CO"}
IAQI_KEYS = {"PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "CO": "co"}
SLOT_STEP = {GRANULARITY_5MIN: timedelta(minutes=5), GRANULARITY_HOUR: timedelta(hours=1)}
PM25_HOLD_PERIODS = 1
FIVE_MIN_HOLD_PERIODS = 2


def new_rule_state() -> dict[str, Any]:
    """alert_state 单实例初始值（引擎 streak 与推送状态共用结构）。"""
    return {
        "last_push_ts": None,
        "last_air_level": None,
        "armed": True,
        "recover_cnt": 0,
        "streak_cnt": 0,
        "last_value": None,
        "start_value": None,
        "last_trigger_threshold": None,
        "first_event_id": None,
    }


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def has_mark(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def slot_of(value: datetime, grain: str) -> datetime:
    """对齐到 5 分钟槽或整点槽（Asia/Shanghai）。"""
    if not isinstance(value, datetime):
        raise TypeError(f"datetime required, got {type(value)!r}")
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ_SHANGHAI)
    value = value.astimezone(TZ_SHANGHAI)
    if grain == GRANULARITY_5MIN:
        return value.replace(minute=(value.minute // 5) * 5, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)


def valid_value(row: dict[str, Any], column: str) -> float | None:
    """单条记录的参数有效值：缺测/负值/带质控标记均视为空值。"""
    if row.get("data_source") == "minute" and has_mark(row.get(f"{column}_mark")):
        return None
    return as_float(row.get(column))


def ge1(value: float, threshold: float) -> bool:
    """数值比较统一约定：保留 1 位小数后比较。"""
    return round(float(value), 1) >= round(float(threshold), 1)


def level_name_for(pollutant: str, concentration: Any) -> str | None:
    """按 HJ 633—2026 计算单因子 1h IAQI 并定档。

    PM2.5/PM10 使用日平均断点，其余因子使用 1 小时断点；断点表复用
    xuchang_city_exceedance.aqi（已按 2026 过渡限值收严 PM2.5/PM10）。
    """
    key = IAQI_KEYS.get(pollutant)
    if key is None:
        return None
    score = iaqi(key, concentration)
    code = aqi_level(score)
    return LEVEL_NAMES.get(code) if code is not None else None


def level_code(level_name: str | None) -> int | None:
    if not level_name:
        return None
    return LEVEL_CODES.get(str(level_name))


def hourly_levels(
    rows: list[dict[str, Any]],
    hour: datetime,
    allowlist: set[str] | None,
) -> dict[tuple[str, str], str]:
    """指定整点槽内每个站点、每个污染物的 1h IAQI 等级。"""
    levels: dict[tuple[str, str], str] = {}
    for row in rows:
        if row.get("data_source") != "hour":
            continue
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime):
            continue
        if slot_of(timestamp, GRANULARITY_HOUR) != hour:
            continue
        station_id = str(row.get("station_id") or "")
        if not station_id or (allowlist is not None and station_id not in allowlist):
            continue
        for pollutant in POLLUTANTS:
            value = valid_value(row, POLLUTANT_COLUMNS[pollutant])
            if value is None:
                continue
            name = level_name_for(pollutant, value)
            if name is not None:
                levels[(station_id, pollutant)] = name
    return levels


def _candidate(
    *,
    rule_type: str,
    slot: datetime,
    grain: str,
    station_id: str,
    station_name: str | None,
    pollutant: str,
    value: float,
    level_name: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    data_source = "minute" if grain == GRANULARITY_5MIN else "hour"
    alert: dict[str, Any] = {
        "event_id": (
            f"xuchang-air-{rule_type}-{slot:%Y%m%d%H%M}-{station_id}-"
            f"{pollutant.lower().replace('.', '')}"
        ),
        "event_type": EVENT_TYPE,
        "occurred_at": slot.isoformat(),
        "city": "许昌市",
        "station_id": station_id,
        "station_name": station_name or station_id,
        "target_pollutant": pollutant,
        "observed_indicator": OBSERVED_INDICATORS[pollutant],
        "data_source": data_source,
        "measurement_granularity": grain,
        "station_value": value,
        "rule": rule_type,
        "rule_type": rule_type,
        "rule_label": RULE_LABELS[rule_type],
        "rule_priority": RULE_PRIORITY[rule_type],
        "air_quality_level": level_name,
        "air_quality_level_code": LEVEL_CODES[level_name],
        "detail": detail,
        "recovery_threshold": detail.get("threshold"),
    }
    if rule_type == "spatial_outlier":
        peer = detail.get("peer_mean")
        alert.update(
            peer_mean=peer,
            peer_baseline=peer,
            peer_baseline_method="regional_mean_others",
            absolute_delta=detail.get("absolute_delta"),
            deviation_ratio=detail.get("deviation_ratio"),
            deviation_percent=detail.get("deviation_percent"),
            peer_station_count=detail.get("peer_station_count"),
        )
    elif rule_type == "continuous_rise":
        alert.update(
            rise_window_values=detail.get("rise_window_values"),
            rise_count=detail.get("rise_count"),
            total_rise_rate=detail.get("total_rise_rate"),
            total_rise_abs=detail.get("total_rise_abs"),
        )
    elif rule_type == "sudden_rise":
        alert.update(
            baseline=detail.get("baseline"),
            rise_ratio=detail.get("rise_ratio"),
            rise_percent=detail.get("rise_percent"),
        )
    return alert


def _current_slot_values(
    rows: list[dict[str, Any]],
    slot: datetime,
    column: str,
    grain: str,
    allowlist: set[str] | None,
) -> dict[str, tuple[float, dict[str, Any]]]:
    source = "minute" if grain == GRANULARITY_5MIN else "hour"
    values: dict[str, tuple[float, dict[str, Any]]] = {}
    for row in rows:
        if row.get("data_source") != source:
            continue
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime) or slot_of(timestamp, grain) != slot:
            continue
        station_id = str(row.get("station_id") or "")
        if not station_id or (allowlist is not None and station_id not in allowlist):
            continue
        value = valid_value(row, column)
        if value is None:
            continue
        values[station_id] = (value, row)
    return values


def _history_series(
    rows: list[dict[str, Any]],
    column: str,
    before_slot: datetime,
    grain: str,
    allowlist: set[str] | None,
) -> dict[str, list[tuple[datetime, float]]]:
    source = "minute" if grain == GRANULARITY_5MIN else "hour"
    series: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        if row.get("data_source") != source:
            continue
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime):
            continue
        slot = slot_of(timestamp, grain)
        if slot >= before_slot:
            continue
        station_id = str(row.get("station_id") or "")
        if not station_id or (allowlist is not None and station_id not in allowlist):
            continue
        value = valid_value(row, column)
        if value is None:
            continue
        series[station_id].append((slot, value))
    for entries in series.values():
        entries.sort()
    return dict(series)


def _tail_values(
    series: list[tuple[datetime, float]] | None,
    count: int,
    step: timedelta,
    end_slot: datetime,
    grain: str,
) -> list[float] | None:
    """取恰好连续到 end_slot 的最近 count 个值；缺槽返回 None。"""
    if not series or len(series) < count:
        return None
    tail = series[-count:]
    for index, (timestamp, _value) in enumerate(tail):
        expected = end_slot - step * (count - 1 - index)
        if slot_of(timestamp, grain) != expected:
            return None
    return [value for _timestamp, value in tail]


def _series_with_current(
    history: list[tuple[datetime, float]] | None,
    slot: datetime,
    value: float,
) -> list[tuple[datetime, float]]:
    return list(history or []) + [(slot, value)]


def _previous_values(
    series: list[tuple[datetime, float]],
    count: int,
    step: timedelta,
    slot: datetime,
    grain: str,
) -> list[float] | None:
    """当前槽之前的最近 count 个连续值（不含当前槽）。"""
    tail = _tail_values(series, count + 1, step, slot, grain)
    return tail[:count] if tail else None


def rule_ds(
    value: float,
    baseline_value: float | None,
    pollutant: str,
    level_name: str | None,
    config: AirAlertRuleConfig,
    peer_same_direction_count: int = 0,
) -> tuple[int, dict[str, Any]]:
    """单点突升：Δ >= MAX(基线 × 比例, 绝对增量)，单窗口成立。"""
    if baseline_value is None or baseline_value < 0 or level_name is None:
        return 0, {}
    ratio, absolute = config.thresholds(pollutant, "sudden_rise", level_name)
    delta = value - baseline_value
    ratio_threshold = baseline_value * ratio
    threshold = max(ratio_threshold, absolute)
    detail: dict[str, Any] = {
        "baseline": round(baseline_value, 3),
        "delta": round(delta, 3),
        "ratio": ratio,
        "ratio_threshold": round(ratio_threshold, 3),
        "absolute_threshold": absolute,
        "threshold": round(threshold, 3),
        "rise_percent": round(delta / baseline_value * 100, 1) if baseline_value > 0 else None,
        "peer_same_direction_count": peer_same_direction_count,
        "recovery_threshold": round(threshold, 3),
    }
    if peer_same_direction_count >= config.neighbor_same_direction_count:
        detail["suppressed_reason"] = "neighbor_same_direction"
        return 0, detail
    if delta >= 0 and ge1(delta, threshold):
        return 1, detail
    return 0, detail


def rule_cl(
    window_values: list[float],
    baseline_value: float,
    pollutant: str,
    level_name: str | None,
    config: AirAlertRuleConfig,
) -> tuple[int, dict[str, Any]]:
    """连续抬升：3 个窗口值逐段不降，每段增量 >= 总增量 15%，累计达到阈值。

    段增量 = [起点−基线, v2−起点, 末值−v2]；起点固定为 3 段中的第一段，
    基线为抬升起点前 15 分钟（PM2.5 前 1 小时）均值。
    """
    if level_name is None or len(window_values) != 3:
        return 0, {}
    total = window_values[-1] - baseline_value
    segments = [
        window_values[0] - baseline_value,
        window_values[1] - window_values[0],
        window_values[2] - window_values[1],
    ]
    ratio, absolute = config.thresholds(pollutant, "continuous_rise", level_name)
    threshold = max(baseline_value * ratio, absolute)
    detail: dict[str, Any] = {
        "baseline": round(baseline_value, 3),
        "total_rise_abs": round(total, 3),
        "total_rise_rate": round(total / baseline_value, 4) if baseline_value > 0 else None,
        "segment_gains": [round(segment, 3) for segment in segments],
        "ratio": ratio,
        "ratio_threshold": round(baseline_value * ratio, 3),
        "absolute_threshold": absolute,
        "threshold": round(threshold, 3),
        "rise_window_values": list(window_values),
        "rise_count": 3,
        "recovery_threshold": round(threshold, 3),
    }
    if total <= 0:
        return 0, detail
    if any(segment < 0 for segment in segments):
        return 0, detail
    if not all(ge1(segment, total * config.cl_segment_min_share) for segment in segments):
        return 0, detail
    if ge1(total, threshold):
        return 1, detail
    return 0, detail


def rule_ol(
    value: float,
    peer_mean: float | None,
    pollutant: str,
    level_name: str | None,
    config: AirAlertRuleConfig,
    state: dict[str, Any],
    hold_periods: int,
) -> tuple[int, dict[str, Any]]:
    """站点离群：本站 vs 其余有效站同刻平均值。"""
    if peer_mean is None or peer_mean <= 0 or level_name is None:
        state["streak_cnt"] = 0
        return 0, {}
    ratio, absolute = config.thresholds(pollutant, "spatial_outlier", level_name)
    delta = value - peer_mean
    threshold = max(peer_mean * ratio, absolute)
    detail: dict[str, Any] = {
        "peer_mean": round(peer_mean, 3),
        "absolute_delta": round(delta, 3),
        "deviation_ratio": round(delta / peer_mean, 3),
        "deviation_percent": round(delta / peer_mean * 100, 1),
        "peer_station_count": None,
        "ratio": ratio,
        "ratio_threshold": round(peer_mean * ratio, 3),
        "absolute_threshold": absolute,
        "threshold": round(threshold, 3),
        "hold_periods": hold_periods,
        "recovery_threshold": round(threshold, 3),
    }
    if delta >= 0 and ge1(delta, threshold):
        state["streak_cnt"] = int(state.get("streak_cnt") or 0) + 1
        detail["hold_streak"] = state["streak_cnt"]
        if state["streak_cnt"] >= hold_periods:
            return 1, detail
        return 0, detail
    state["streak_cnt"] = 0
    return 0, detail


@dataclass
class CycleOutcome:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    # (grain, station_id, pollutant) -> 本槽有效值（展示/回溯用）。
    current_values: dict[tuple[str, str, str], float] = field(default_factory=dict)
    # (grain, station_id, pollutant, rule_type) -> 与本规则阈值同口径的恢复
    # 指标：DS/CL 为相对基线的增量，OL 为相对其余站点均值的偏差。恢复防抖
    # 必须用该指标比较，不能用原始浓度比较增量阈值。
    recovery_metrics: dict[tuple[str, str, str, str], float] = field(default_factory=dict)
    # CL 区域合并被抑制的候选（同窗口 >=N 站命中时只留最大站）。
    region_merged: list[dict[str, Any]] = field(default_factory=list)


def merge_regional_rises(
    candidates: list[dict[str, Any]],
    config: AirAlertRuleConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """连续抬升区域合并：同污染物同窗口 >=N 站命中 CL 时只推最大站一条。

    主告警取累计抬升绝对量最大的站点，detail 附全站清单
    ``region_stations``；其余站点候选原样返回，由推送链以
    ``regional_merge`` 抑制入库（不推送但保留流水）。DS/OL 候选不受影响。
    """
    min_sites = int(getattr(config, "cl_region_merge_sites", 0) or 0)
    if min_sites <= 0:
        return candidates, []
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for alert in candidates:
        if alert.get("rule_type") == "continuous_rise":
            grouped[(str(alert.get("measurement_granularity")), str(alert.get("target_pollutant")))].append(alert)
        else:
            kept.append(alert)
    for items in grouped.values():
        if len(items) < min_sites:
            kept.extend(items)
            continue
        primary = max(items, key=lambda a: float(a.get("total_rise_abs") or a.get("detail", {}).get("total_rise_abs") or 0))
        primary["detail"]["region_stations"] = [
            {
                "station_id": item.get("station_id"),
                "station_name": item.get("station_name"),
                "station_value": item.get("station_value"),
                "total_rise_abs": (item.get("detail") or {}).get("total_rise_abs"),
                "air_quality_level": item.get("air_quality_level"),
            }
            for item in sorted(items, key=lambda a: str(a.get("station_id")))
            if item is not primary
        ]
        primary["region_merged_count"] = len(items)
        kept.append(primary)
        suppressed.extend(item for item in items if item is not primary)
    return kept, suppressed


def _reset_missing_streaks(states: Any, grain: str, pollutant: str, present_stations: set[str]) -> None:
    """当前槽无有效值的站点：OL 连续性中断，streak 清零。"""
    iterate = getattr(states, "iterate", None)
    if not iterate:
        return
    for station_id, rule_type, state in iterate(grain, pollutant):
        if station_id in present_stations:
            continue
        if rule_type == "OL":
            state["streak_cnt"] = 0


def _peer_mean(
    values: dict[str, float],
    station_id: str,
    min_region_stations: int,
) -> tuple[float | None, int]:
    """其余有效站简单平均值；有效站总数不足时返回 None。"""
    if len(values) < min_region_stations:
        return None, max(len(values) - 1, 0)
    peers = [value for sid, value in values.items() if sid != station_id]
    if len(peers) < min_region_stations - 1:
        return None, len(peers)
    return mean(peers), len(peers)


def evaluate_five_minute_cycle(
    rows: list[dict[str, Any]],
    *,
    target_slot: datetime,
    config: AirAlertRuleConfig,
    states: Any,
    expected_minute_count: int | None = None,
    station_allowlist: set[str] | None = None,
) -> CycleOutcome:
    """一个 5 分钟槽的全量判定（DS/CL/OL）。"""
    outcome = CycleOutcome()
    grain = GRANULARITY_5MIN
    step = SLOT_STEP[grain]
    # 污染等级按该污染物 1 小时平均定档：5 分钟规则使用上一完整小时。
    levels = hourly_levels(rows, slot_of(target_slot, GRANULARITY_HOUR) - timedelta(hours=1), station_allowlist)

    for pollutant in FIVE_MIN_POLLUTANTS:
        column = POLLUTANT_COLUMNS[pollutant]
        current = _current_slot_values(rows, target_slot, column, grain, station_allowlist)
        history = _history_series(rows, column, target_slot, grain, station_allowlist)
        available = len(current)
        outcome.checks.append({
            "time": target_slot.isoformat(),
            "pollutant": pollutant,
            "observed_indicator": OBSERVED_INDICATORS[pollutant],
            "available_station_count": available,
            "expected_station_count": expected_minute_count,
            "data_rate": round(available / expected_minute_count, 3) if expected_minute_count else None,
            "level_available_count": sum(1 for sid in current if (sid, pollutant) in levels),
            "status": "checked",
        })
        all_values = {sid: value for sid, (value, _row) in current.items()}

        # 先算每站 DS 上下文，供“邻站未同向”判定。
        ds_context: dict[str, dict[str, Any]] = {}
        series_by_station: dict[str, list[tuple[datetime, float]]] = {}
        for station_id, (value, row) in current.items():
            series = _series_with_current(history.get(station_id), target_slot, value)
            series_by_station[station_id] = series
            level = levels.get((station_id, pollutant))
            if level is None:
                continue
            previous = _previous_values(series, 3, step, target_slot, grain)
            if previous is None:
                continue
            baseline = mean(previous)
            ratio, absolute = config.thresholds(pollutant, "sudden_rise", level)
            threshold = max(baseline * ratio, absolute)
            ds_context[station_id] = {
                "baseline": baseline,
                "delta": value - baseline,
                "hit": (value - baseline) >= 0 and ge1(value - baseline, threshold),
                "level": level,
                "station_name": row.get("name") or row.get("station_name"),
            }

        for station_id, (value, row) in sorted(current.items()):
            outcome.current_values[(grain, station_id, pollutant)] = value
            station_name = row.get("name") or row.get("station_name")
            level = levels.get((station_id, pollutant))

            # 恢复防抖指标：与本规则阈值同口径（增量/偏差，而非浓度）。
            context = ds_context.get(station_id)
            if context is not None:
                outcome.recovery_metrics[(grain, station_id, pollutant, "sudden_rise")] = (
                    value - context["baseline"]
                )

            # DS：单点突升，单窗口；邻站同向则不判。
            if context is not None:
                peer_same_direction = sum(
                    1 for other, other_ctx in ds_context.items()
                    if other != station_id and other_ctx["hit"]
                )
                hit, detail = rule_ds(
                    value, context["baseline"], pollutant, level, config, peer_same_direction
                )
                if hit:
                    outcome.candidates.append(_candidate(
                        rule_type="sudden_rise", slot=target_slot, grain=grain,
                        station_id=station_id, station_name=station_name, pollutant=pollutant,
                        value=value, level_name=level, detail=detail,
                    ))

            # CL：窗口 = 3 个基线槽 + 3 个抬升值（起点固定为基线后第一值）。
            tail = _tail_values(series_by_station.get(station_id), 6, step, target_slot, grain)
            if tail is not None:
                baseline = mean(tail[:3])
                outcome.recovery_metrics[(grain, station_id, pollutant, "continuous_rise")] = (
                    value - baseline
                )
            if tail is not None and level is not None:
                baseline = mean(tail[:3])
                hit, detail = rule_cl(tail[3:], baseline, pollutant, level, config)
                if hit:
                    outcome.candidates.append(_candidate(
                        rule_type="continuous_rise", slot=target_slot, grain=grain,
                        station_id=station_id, station_name=station_name, pollutant=pollutant,
                        value=value, level_name=level, detail=detail,
                    ))

            # OL：有效站最少 4 个；PM2.5 单窗口、其他连续 2 窗口。
            peer_mean, peer_count = _peer_mean(all_values, station_id, config.min_region_stations)
            if peer_mean is not None:
                outcome.recovery_metrics[(grain, station_id, pollutant, "spatial_outlier")] = (
                    value - peer_mean
                )
            if peer_mean is not None and level is not None:
                hit, detail = rule_ol(
                    value, peer_mean, pollutant, level, config,
                    states.instance(grain, station_id, pollutant, "OL"),
                    PM25_HOLD_PERIODS if pollutant == "PM2.5" else FIVE_MIN_HOLD_PERIODS,
                )
                if hit:
                    detail["peer_station_count"] = peer_count
                    outcome.candidates.append(_candidate(
                        rule_type="spatial_outlier", slot=target_slot, grain=grain,
                        station_id=station_id, station_name=station_name, pollutant=pollutant,
                        value=value, level_name=level, detail=detail,
                    ))

        _reset_missing_streaks(states, grain, pollutant, set(current))

    outcome.candidates, outcome.region_merged = merge_regional_rises(outcome.candidates, config)
    return outcome


def evaluate_pm25_hourly_cycle(
    rows: list[dict[str, Any]],
    *,
    target_hour: datetime,
    config: AirAlertRuleConfig,
    states: Any,
    expected_hour_count: int | None = None,
    station_allowlist: set[str] | None = None,
) -> CycleOutcome:
    """PM2.5 小时版判定：DS/CL/OL 全部使用小时序列。"""
    outcome = CycleOutcome()
    grain = GRANULARITY_HOUR
    step = SLOT_STEP[grain]
    pollutant = "PM2.5"
    column = POLLUTANT_COLUMNS[pollutant]
    # PM2.5 当前值就是小时值，等级直接用该小时值定档。
    levels = hourly_levels(rows, target_hour, station_allowlist)
    current = _current_slot_values(rows, target_hour, column, grain, station_allowlist)
    history = _history_series(rows, column, target_hour, grain, station_allowlist)
    available = len(current)
    outcome.checks.append({
        "time": target_hour.isoformat(),
        "pollutant": pollutant,
        "observed_indicator": OBSERVED_INDICATORS[pollutant],
        "available_station_count": available,
        "expected_station_count": expected_hour_count,
        "data_rate": round(available / expected_hour_count, 3) if expected_hour_count else None,
        "level_available_count": sum(1 for sid in current if (sid, pollutant) in levels),
        "status": "checked",
        "granularity": grain,
    })
    all_values = {sid: value for sid, (value, _row) in current.items()}

    ds_context: dict[str, dict[str, Any]] = {}
    series_by_station: dict[str, list[tuple[datetime, float]]] = {}
    for station_id, (value, row) in current.items():
        series = _series_with_current(history.get(station_id), target_hour, value)
        series_by_station[station_id] = series
        level = levels.get((station_id, pollutant))
        if level is None:
            continue
        previous = _previous_values(series, config.pm25_ds_baseline_hours, step, target_hour, grain)
        if previous is None:
            continue
        baseline = mean(previous)
        ratio, absolute = config.thresholds(pollutant, "sudden_rise", level)
        threshold = max(baseline * ratio, absolute)
        ds_context[station_id] = {
            "baseline": baseline,
            "delta": value - baseline,
            "hit": (value - baseline) >= 0 and ge1(value - baseline, threshold),
            "level": level,
            "station_name": row.get("name") or row.get("station_name"),
        }

    for station_id, (value, row) in sorted(current.items()):
        outcome.current_values[(grain, station_id, pollutant)] = value
        station_name = row.get("name") or row.get("station_name")
        level = levels.get((station_id, pollutant))

        context = ds_context.get(station_id)
        if context is not None:
            outcome.recovery_metrics[(grain, station_id, pollutant, "sudden_rise")] = (
                value - context["baseline"]
            )
            peer_same_direction = sum(
                1 for other, other_ctx in ds_context.items()
                if other != station_id and other_ctx["hit"]
            )
            hit, detail = rule_ds(
                value, context["baseline"], pollutant, level, config, peer_same_direction
            )
            if hit:
                outcome.candidates.append(_candidate(
                    rule_type="sudden_rise", slot=target_hour, grain=grain,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, level_name=level, detail=detail,
                ))

        # CL：连续 3 个小时值，基线取抬升起点前一小时（可配置小时数）。
        baseline_hours = max(int(config.pm25_cl_baseline_hours), 1)
        tail = _tail_values(
            series_by_station.get(station_id), baseline_hours + 3, step, target_hour, grain
        )
        if tail is not None:
            outcome.recovery_metrics[(grain, station_id, pollutant, "continuous_rise")] = (
                value - mean(tail[:baseline_hours])
            )
        if tail is not None and level is not None:
            baseline = mean(tail[:baseline_hours])
            hit, detail = rule_cl(tail[baseline_hours:], baseline, pollutant, level, config)
            if hit:
                outcome.candidates.append(_candidate(
                    rule_type="continuous_rise", slot=target_hour, grain=grain,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, level_name=level, detail=detail,
                ))

        peer_mean, peer_count = _peer_mean(all_values, station_id, config.min_region_stations)
        if peer_mean is not None:
            outcome.recovery_metrics[(grain, station_id, pollutant, "spatial_outlier")] = (
                value - peer_mean
            )
        if peer_mean is not None and level is not None:
            hit, detail = rule_ol(
                value, peer_mean, pollutant, level, config,
                states.instance(grain, station_id, pollutant, "OL"), PM25_HOLD_PERIODS,
            )
            if hit:
                detail["peer_station_count"] = peer_count
                outcome.candidates.append(_candidate(
                    rule_type="spatial_outlier", slot=target_hour, grain=grain,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, level_name=level, detail=detail,
                ))

    _reset_missing_streaks(states, grain, pollutant, set(current))
    outcome.candidates, outcome.region_merged = merge_regional_rises(outcome.candidates, config)
    return outcome
