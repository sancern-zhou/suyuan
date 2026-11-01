"""分级告警规则引擎（R1 限值突破 / R2 突升 / R3 连续抬升 / R4 空间离群）。

实现《空气质量数据告警推送系统——算法需求文档》V1.0 §3-§8，适配许昌中大
站点表：PM10/SO2/NO2/CO/O3 用 5 分钟表逐槽判定，PM2.5 用小时表按 §8
小时版判定（同一引擎、独立状态键）。数据有效性约定映射：中大 ``_mark``
列有标记视为 P/C（异常剔除/校准），缺测或负值视为 M（缺测），均不参与
基线与判定。

规则函数按文档伪代码逐条实现并维护 alert_state 中的 streak 字段；
推送管控（冷却/防抖/限额/合并）在 push_control 模块，本模块只产出
候选告警。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 与 service.EVENT_TYPE 保持同一取值（事件由同一条工作流链路消费）。
EVENT_TYPE = "xuchang.station_deviation.alert_created"

GRANULARITY_5MIN = "5min"
GRANULARITY_HOUR = "hour"

POLLUTANT_COLUMNS = {
    "PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "CO": "co", "O3": "o3",
}
OBSERVED_INDICATORS = {"PM2.5": "PM2.5", "PM10": "PM10", "SO2": "SO2", "NO2": "NO2", "CO": "CO", "O3": "O3"}
FIVE_MIN_POLLUTANTS = ("PM10", "SO2", "NO2", "CO", "O3")
SLOT_STEP = {GRANULARITY_5MIN: timedelta(minutes=5), GRANULARITY_HOUR: timedelta(hours=1)}

RULE_LABELS = {
    "limit_breach": "限值突破",
    "sudden_rise": "突升",
    "continuous_rise": "连续抬升",
    "spatial_outlier": "空间离群",
}
LEVEL_NAMES = {1: "一级", 2: "二级", 3: "三级"}
AQI_LEVEL_CODES = {"优": 0, "良": 1, "轻度污染": 2, "中度污染": 3, "重度污染": 4, "严重污染": 5}
# R1 分档查表用的档位名（§4.1 步骤 2：优良并档、重度严重并档）。
R1_LEVEL_BINS = {"优": "良", "良": "良", "轻度污染": "轻度", "中度污染": "中度", "重度污染": "重度及以上", "严重污染": "重度及以上"}


def new_rule_state() -> dict[str, Any]:
    """alert_state 单实例初始值（文档 §2.4）。"""
    return {
        "level": 0,
        "last_push_ts": None,
        "last_level": 0,
        "armed": True,
        "recover_cnt": 0,
        "streak_cnt": 0,
        "last_value": None,
        "start_value": None,
        "last_trigger_threshold": None,
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
    """数值比较统一约定（§3.5）：保留 1 位小数后比较。"""
    return round(float(value), 1) >= round(float(threshold), 1)


def delta_ratio(base_ratio: float, level_code: int | None, config: AirAlertRuleConfig) -> float:
    """抬升比例的污染等级修正（§3.4）。level_code 缺失按优/良处理。"""
    code = 1 if level_code is None else level_code
    if code <= 1:
        return base_ratio + config.r2_level_adjust_good
    if code >= 4:
        return max(base_ratio + config.r2_level_adjust_heavy, config.r2_min_ratio)
    return base_ratio


def r1_level_bin(level_name: str | None) -> str:
    if not level_name:
        return "良"
    return R1_LEVEL_BINS.get(level_name, "良")


def aqi_level_code(level_name: str | None) -> int | None:
    if not level_name:
        return None
    return AQI_LEVEL_CODES.get(level_name)


def baseline(series: list[tuple[datetime, float]] | None, window: int, min_valid: int) -> float | None:
    """基线 = 当前槽之前最近 window 个有效值的中位数（§3.1）。"""
    if not series:
        return None
    values = [value for _, value in series[-window:]]
    if len(values) < min_valid:
        return None
    return median(values)


def trim_mean_others(values_by_station: dict[str, float], station_id: str) -> float | None:
    """除本站外去极值均值（§3.3）：去掉最大、最小后取均值，剩余 ≥3 才计算。

    6 站口径下即其余 5 站全部有效才计算；不足时返回 None，跳过 R4（§11）。
    """
    others = sorted(value for sid, value in values_by_station.items() if sid != station_id)
    if len(others) < 5:
        return None
    trimmed = others[1:-1]
    return sum(trimmed) / len(trimmed)


def _pollutant_slug(pollutant: str) -> str:
    return pollutant.lower().replace(".", "")


def _candidate(
    *,
    rule_type: str,
    level: int,
    slot: datetime,
    grain: str,
    station_id: str,
    station_name: str | None,
    pollutant: str,
    value: float,
    detail: dict[str, Any],
) -> dict[str, Any]:
    data_source = "minute" if grain == GRANULARITY_5MIN else "hour"
    alert: dict[str, Any] = {
        "event_id": (
            f"xuchang-air-{rule_type}-{slot:%Y%m%d%H%M}-{station_id}-{_pollutant_slug(pollutant)}-{level}"
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
        "alert_level": level,
        "alert_level_name": LEVEL_NAMES[level],
        "detail": detail,
        "recovery_threshold": detail.get("recovery_threshold"),
    }
    if rule_type == "spatial_outlier":
        peer = detail.get("peer_trim_mean")
        alert.update(
            peer_mean=peer,
            peer_baseline=peer,
            peer_baseline_method="trimmed_mean_others",
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


def rule_r1(
    value: float,
    pollutant: str,
    level_bin: str,
    limit_version: dict[str, Any],
    config: AirAlertRuleConfig,
) -> tuple[int, dict[str, Any]]:
    """限值突破（§4）：值≥T 三级、≥T×1.2 二级、≥T×1.5 或 1h 国标限值一级。"""
    tiers = limit_version.get("tiers", {}).get(pollutant, {})
    threshold = tiers.get(level_bin)
    if threshold is None:
        return 0, {}
    limit_1h = limit_version.get("limit_1h", {}).get(pollutant)
    detail: dict[str, Any] = {
        "limit_bin": level_bin,
        "limit_threshold": threshold,
        "limit_version": limit_version.get("name"),
        "limit_1h": limit_1h,
    }
    if limit_1h and ge1(value, limit_1h):
        return 1, {**detail, "trigger": "达到1小时国标限值", "recovery_threshold": threshold}
    if ge1(value, threshold * config.r1_primary_multiple):
        return 1, {**detail, "trigger": "达到一级阈值（T×1.5）", "recovery_threshold": threshold}
    if ge1(value, threshold * config.r1_secondary_multiple):
        return 2, {**detail, "trigger": "达到二级阈值（T×1.2）", "recovery_threshold": threshold}
    if ge1(value, threshold):
        return 3, {**detail, "trigger": "达到分档限值", "recovery_threshold": threshold}
    return 0, detail


def rule_r2(
    current: float,
    base: float | None,
    pollutant: str,
    level_code: int | None,
    config: AirAlertRuleConfig,
    state: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """突升（§5）：对比基线三档比例，三级需连续确认，二级/一级即时。"""
    floor = config.r2_floors.get(pollutant)
    if base is None or base <= 0 or floor is None or current < floor:
        # 基线不可用或低于绝对底线：本轮不判定，连续确认按间断清零（§5.2）。
        state["streak_cnt"] = 0
        return 0, {}
    thresholds: dict[int, float] = {}
    ratios: dict[int, float] = {}
    hit = 0
    for level in (3, 2, 1):
        ratio = delta_ratio(config.r2_ratios[level], level_code, config)
        threshold = base * (1 + ratio)
        ratios[level] = ratio
        thresholds[level] = threshold
        if ge1(current, threshold):
            # 级别数字越小越严重：同时满足多档时取最严档（文档 §5.1 表）。
            hit = level
    detail: dict[str, Any] = {
        "baseline": base,
        "floor": floor,
        "rise_ratios_effective": ratios,
        "rise_thresholds": thresholds,
    }
    if hit == 3:
        state["streak_cnt"] += 1
        detail["confirm_streak"] = state["streak_cnt"]
        if state["streak_cnt"] >= config.r2_confirm_periods:
            detail.update(
                rise_ratio=ratios[3],
                rise_percent=round(ratios[3] * 100, 1),
                recovery_threshold=thresholds[3],
            )
            return 3, detail
        return 0, detail
    if hit == 0:
        # 三级条件未满足即视为间断（§5.2）；命中二/一级时按文档伪代码
        # 不动 streak（该周期同样满足三级阈值，连续性未中断）。
        state["streak_cnt"] = 0
    if hit >= 2:
        detail.update(
            rise_ratio=ratios[hit],
            rise_percent=round(ratios[hit] * 100, 1),
            recovery_threshold=thresholds[hit],
        )
        return hit, detail
    return 0, detail


def rule_r3(
    current: float,
    prev_value: float | None,
    prev_continuous: bool,
    pollutant: str,
    config: AirAlertRuleConfig,
    state: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """连续抬升（§6）：逐期涨幅 ≥2% 计连续，周期数与累计涨幅取先满足的高档。"""
    if not prev_continuous or not prev_value or prev_value <= 0:
        state["streak_cnt"] = 0
        state["start_value"] = None
        state["last_value"] = current
        return 0, {}
    step_pct = (current - prev_value) / prev_value
    if step_pct >= config.r3_step_min:
        if not state["streak_cnt"]:
            state["start_value"] = prev_value
        state["streak_cnt"] += 1
    else:
        state["streak_cnt"] = 0
        state["start_value"] = None
    state["last_value"] = current
    detail: dict[str, Any] = {"streak_cnt": state["streak_cnt"], "step_pct": round(step_pct, 4)}
    floor = config.r2_floors.get(pollutant)
    if state["streak_cnt"] < config.r3_periods[3] or (floor is not None and current < floor):
        return 0, detail
    start = state["start_value"]
    if not start or start <= 0:
        return 0, detail
    # 与 §3.5 一致：累计涨幅按 value >= base × (1 + ratio) 比较；先判一级，
    # 即周期数与累计涨幅取先满足者对应的最高档（§6.3）。
    for level in (1, 2, 3):
        if state["streak_cnt"] >= config.r3_periods[level] and ge1(
            current, start * (1 + config.r3_cum_gains[level])
        ):
            detail.update(
                start_value=start,
                cumulative_gain=round((current - start) / start, 4),
                recovery_threshold=start * (1 + config.r3_cum_gains[level]),
            )
            return level, detail
    return 0, detail


def rule_r4(
    current: float,
    others_mean: float | None,
    pollutant: str,
    level_code: int | None,
    config: AirAlertRuleConfig,
    state: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """空间离群（§7）：对比其余站点去极值均值，重污染放宽倍率，低级别需持续确认。"""
    if not others_mean or others_mean <= 0:
        state["streak_cnt"] = 0
        return 0, {}
    diff_floor = config.r4_diff_floors.get(pollutant)
    absolute_delta = current - others_mean
    detail: dict[str, Any] = {
        "peer_trim_mean": round(others_mean, 3),
        "absolute_delta": round(absolute_delta, 3),
        "diff_floor": diff_floor,
        "peer_station_count": 5,
        "deviation_ratio": round(absolute_delta / others_mean, 3),
        "deviation_percent": round(absolute_delta / others_mean * 100, 1),
    }
    if diff_floor is None or absolute_delta < diff_floor:
        state["streak_cnt"] = 0
        return 0, detail
    multiples = dict(config.r4_multiples)
    if level_code is not None and level_code >= 4:
        multiples = {level: m - config.r4_heavy_relief for level, m in multiples.items()}
    detail["multiples_effective"] = multiples
    thresholds = {level: others_mean * m for level, m in multiples.items()}
    hit = 0
    for level in (3, 2, 1):
        if ge1(current, thresholds[level]):
            # 级别数字越小越严重：同时满足多档时取最严档。
            hit = level
    hold = config.r4_hold_periods
    if hit >= 2 and hold.get(hit, 0) > 0:
        state["streak_cnt"] += 1
        detail["hold_streak"] = state["streak_cnt"]
        if state["streak_cnt"] >= hold[hit]:
            detail["recovery_threshold"] = thresholds[hit]
            return hit, detail
        return 0, detail
    if hit == 0:
        state["streak_cnt"] = 0
    if hit == 1:
        detail["recovery_threshold"] = thresholds[1]
    return hit, detail


@dataclass
class CycleOutcome:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    # (grain, station_id, pollutant) -> 本槽有效值，供恢复防抖与后续比对使用。
    current_values: dict[tuple[str, str, str], float] = field(default_factory=dict)
    # 满足 R2/R3 三级条件（不论确认）的站点，供 §7.2 区域过程豁免判定。
    region_event_stations: list[str] = field(default_factory=list)


def _reset_missing_streaks(
    states: Any, grain: str, pollutant: str, present_stations: set[str]
) -> None:
    """当前槽无有效值的 (station, pollutant) 实例：连续性中断，streak 清零（§11）。"""
    iterate = getattr(states, "iterate", None)
    if not iterate:
        return
    for station_id, rule_type, state in iterate(grain, pollutant):
        if station_id in present_stations:
            continue
        if rule_type in ("R2", "R3", "R4"):
            state["streak_cnt"] = 0
            if rule_type == "R3":
                state["start_value"] = None


def evaluate_five_minute_cycle(
    rows: list[dict[str, Any]],
    *,
    target_slot: datetime,
    config: AirAlertRuleConfig,
    states: Any,
    level_name: str | None,
    expected_minute_count: int | None = None,
    station_allowlist: set[str] | None = None,
) -> CycleOutcome:
    """一个 5 分钟槽的全量判定（§10 主流程的规则部分）。

    states 需提供 ``instance(grain, station, pollutant, rule) -> dict`` 与
    ``iterate(grain, pollutant) -> [(station, rule, state), ...]``。
    """
    outcome = CycleOutcome()
    level_bin = r1_level_bin(level_name)
    level_code = aqi_level_code(level_name)
    limit_version = config.active_limit_version(target_slot.astimezone(TZ_SHANGHAI).date())
    raw_level3_stations: set[str] = set()

    for pollutant in FIVE_MIN_POLLUTANTS:
        column = POLLUTANT_COLUMNS[pollutant]
        current = _current_slot_values(rows, target_slot, column, GRANULARITY_5MIN, station_allowlist)
        history = _history_series(rows, column, target_slot, GRANULARITY_5MIN, station_allowlist)
        available = len(current)
        outcome.checks.append({
            "time": target_slot.isoformat(),
            "pollutant": pollutant,
            "observed_indicator": OBSERVED_INDICATORS[pollutant],
            "available_station_count": available,
            "expected_station_count": expected_minute_count,
            "data_rate": round(available / expected_minute_count, 3) if expected_minute_count else None,
            "status": "checked",
        })
        all_values = {sid: value for sid, (value, _) in current.items()}
        peer_means = {sid: trim_mean_others(all_values, sid) for sid in current}
        prev_slot = target_slot - SLOT_STEP[GRANULARITY_5MIN]
        for station_id, (value, row) in sorted(current.items()):
            outcome.current_values[(GRANULARITY_5MIN, station_id, pollutant)] = value
            station_name = row.get("name") or row.get("station_name")
            history_entries = history.get(station_id) or []
            base = baseline(history_entries, config.baseline_window, config.baseline_min_valid)
            prev_continuous = bool(history_entries) and history_entries[-1][0] == prev_slot
            prev_value = history_entries[-1][1] if prev_continuous else None

            def _state(rule: str) -> dict[str, Any]:
                return states.instance(GRANULARITY_5MIN, station_id, pollutant, rule)

            # R1（绝对限值，不依赖基线）。
            hit, detail = rule_r1(value, pollutant, level_bin, limit_version, config)
            if hit:
                outcome.candidates.append(_candidate(
                    rule_type="limit_breach", level=hit, slot=target_slot, grain=GRANULARITY_5MIN,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, detail=detail,
                ))

            # R2（基线中位数 + 等级修正比例）。三级原始条件（不论确认）计入区域过程判定。
            hit, detail = rule_r2(value, base, pollutant, level_code, config, _state("R2"))
            if (
                base is not None and base > 0
                and value >= config.r2_floors.get(pollutant, float("inf"))
                and ge1(value, base * (1 + delta_ratio(config.r2_ratios[3], level_code, config)))
            ):
                raw_level3_stations.add(station_id)
            if hit:
                outcome.candidates.append(_candidate(
                    rule_type="sudden_rise", level=hit, slot=target_slot, grain=GRANULARITY_5MIN,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, detail=detail,
                ))

            # R3（连续逐期上涨）。上一槽缺测视为间断、计数清零（§6.2/§11）。
            r3_state = _state("R3")
            hit, detail = rule_r3(value, prev_value, prev_continuous, pollutant, config, r3_state)
            if hit:
                streak = r3_state["streak_cnt"]
                start = r3_state["start_value"]
                detail.update(
                    rise_window_values=[entry[1] for entry in history_entries[-(streak + 1):]] + [value],
                    rise_count=streak,
                    total_rise_abs=round(value - start, 3),
                    total_rise_rate=round((value - start) / start, 4),
                )
                outcome.candidates.append(_candidate(
                    rule_type="continuous_rise", level=hit, slot=target_slot, grain=GRANULARITY_5MIN,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, detail=detail,
                ))

            # R4（空间离群，其余站去极值均值）。
            hit, detail = rule_r4(value, peer_means.get(station_id), pollutant, level_code, config, _state("R4"))
            if hit:
                outcome.candidates.append(_candidate(
                    rule_type="spatial_outlier", level=hit, slot=target_slot, grain=GRANULARITY_5MIN,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, detail=detail,
                ))
        _reset_missing_streaks(states, GRANULARITY_5MIN, pollutant, set(current))

    outcome.region_event_stations = sorted(raw_level3_stations)
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
    """PM2.5 小时版判定（§8）：同一引擎思路、小时参数、独立状态键（grain=hour）。

    小时版无 R2/R3 一级档、无区域豁免、基线取前 3 小时中位数（<2 跳过）。
    """
    outcome = CycleOutcome()
    level_bin = r1_level_bin(None)
    limit_version = config.active_limit_version(target_hour.astimezone(TZ_SHANGHAI).date())
    column = POLLUTANT_COLUMNS["PM2.5"]
    current = _current_slot_values(rows, target_hour, column, GRANULARITY_HOUR, station_allowlist)
    history = _history_series(rows, column, target_hour, GRANULARITY_HOUR, station_allowlist)
    available = len(current)
    outcome.checks.append({
        "time": target_hour.isoformat(),
        "pollutant": "PM2.5",
        "observed_indicator": "PM2.5",
        "available_station_count": available,
        "expected_station_count": expected_hour_count,
        "data_rate": round(available / expected_hour_count, 3) if expected_hour_count else None,
        "status": "checked",
        "granularity": GRANULARITY_HOUR,
    })
    all_values = {sid: value for sid, (value, _) in current.items()}
    peer_means = {sid: trim_mean_others(all_values, sid) for sid in current}
    prev_slot = target_hour - SLOT_STEP[GRANULARITY_HOUR]

    for station_id, (value, row) in sorted(current.items()):
        outcome.current_values[(GRANULARITY_HOUR, station_id, "PM2.5")] = value
        station_name = row.get("name") or row.get("station_name")
        history_entries = history.get(station_id) or []
        base = baseline(history_entries, config.pm25_baseline_window, config.pm25_baseline_min_valid)
        prev_continuous = bool(history_entries) and history_entries[-1][0] == prev_slot
        prev_value = history_entries[-1][1] if prev_continuous else None

        def _state(rule: str) -> dict[str, Any]:
            return states.instance(GRANULARITY_HOUR, station_id, "PM2.5", rule)

        # R1：直接查 §4.2 PM2.5 行。
        hit, detail = rule_r1(value, "PM2.5", level_bin, limit_version, config)
        if hit:
            outcome.candidates.append(_candidate(
                rule_type="limit_breach", level=hit, slot=target_hour, grain=GRANULARITY_HOUR,
                station_id=station_id, station_name=station_name, pollutant="PM2.5",
                value=value, detail=detail,
            ))

        # R2（小时版）：V≥B×1.25 且 (V−B)≥15 三级；V≥B×1.5 且 (V−B)≥15 二级；均即时。
        state = _state("R2")
        hit = 0
        detail: dict[str, Any] = {"baseline": base, "min_abs_gain": config.pm25_r2_min_abs_gain}
        if base is None or base <= 0:
            state["streak_cnt"] = 0
        else:
            for level, ratio in ((3, config.pm25_r2_t3_ratio), (2, config.pm25_r2_t2_ratio)):
                threshold = base * (1 + ratio)
                if ge1(value, threshold) and ge1(value - base, config.pm25_r2_min_abs_gain):
                    # 后检的二/一级档更严，同时满足时取更严档。
                    hit = level
                    detail.update(
                        rise_ratio=ratio,
                        absolute_gain=round(value - base, 3),
                        recovery_threshold=threshold,
                    )
        if hit:
            outcome.candidates.append(_candidate(
                rule_type="sudden_rise", level=hit, slot=target_hour, grain=GRANULARITY_HOUR,
                station_id=station_id, station_name=station_name, pollutant="PM2.5",
                value=value, detail=detail,
            ))

        # R3（小时版）：逐期涨幅 ≥2% 同 §6.2；三级连续 2 小时且累计 ≥15%，二级 3 小时 ≥30%。
        state = _state("R3")
        hit = 0
        detail = {}
        if not prev_continuous or not prev_value or prev_value <= 0:
            state["streak_cnt"] = 0
            state["start_value"] = None
            state["last_value"] = value
        else:
            step_pct = (value - prev_value) / prev_value
            if step_pct >= config.pm25_r3_step_min:
                if not state["streak_cnt"]:
                    state["start_value"] = prev_value
                state["streak_cnt"] += 1
            else:
                state["streak_cnt"] = 0
                state["start_value"] = None
            state["last_value"] = value
            start = state["start_value"]
            detail = {"streak_cnt": state["streak_cnt"], "step_pct": round(step_pct, 4)}
            # 先判更严的二级档，同时满足时取二级（数字更小更严重）。
            for level, periods, cum in (
                (2, config.pm25_r3_t2_periods, config.pm25_r3_t2_cum),
                (3, config.pm25_r3_t3_periods, config.pm25_r3_t3_cum),
            ):
                if state["streak_cnt"] >= periods and start and ge1(value, start * (1 + cum)):
                    detail.update(
                        start_value=start,
                        cumulative_gain=round((value - start) / start, 4),
                        recovery_threshold=start * (1 + cum),
                    )
                    hit = level
                    break
        if hit:
            streak = state["streak_cnt"]
            start = state["start_value"]
            detail.update(
                rise_window_values=[entry[1] for entry in history_entries[-(streak + 1):]] + [value],
                rise_count=streak,
                total_rise_abs=round(value - start, 3),
                total_rise_rate=round((value - start) / start, 4),
            )
            outcome.candidates.append(_candidate(
                rule_type="continuous_rise", level=hit, slot=target_hour, grain=GRANULARITY_HOUR,
                station_id=station_id, station_name=station_name, pollutant="PM2.5",
                value=value, detail=detail,
            ))

        # R4（小时版）：三级 V≥R×1.5 且差 ≥35 持续 1 小时；二级 V≥R×2.0 且差 ≥35 即时。
        state = _state("R4")
        hit = 0
        detail = {}
        others_mean = peer_means.get(station_id)
        if not others_mean or others_mean <= 0:
            state["streak_cnt"] = 0
        else:
            absolute_delta = value - others_mean
            detail = {
                "peer_trim_mean": round(others_mean, 3),
                "absolute_delta": round(absolute_delta, 3),
                "diff_floor": config.pm25_r4_t3_diff,
                "peer_station_count": 5,
                "deviation_ratio": round(absolute_delta / others_mean, 3),
                "deviation_percent": round(absolute_delta / others_mean * 100, 1),
            }
            if ge1(value, others_mean * config.pm25_r4_t2_multiple) and ge1(absolute_delta, config.pm25_r4_t2_diff):
                detail["recovery_threshold"] = others_mean * config.pm25_r4_t2_multiple
                hit = 2
            elif ge1(value, others_mean * config.pm25_r4_t3_multiple) and ge1(absolute_delta, config.pm25_r4_t3_diff):
                state["streak_cnt"] += 1
                detail["hold_streak"] = state["streak_cnt"]
                if state["streak_cnt"] >= config.pm25_r4_t3_hold_periods:
                    detail["recovery_threshold"] = others_mean * config.pm25_r4_t3_multiple
                    hit = 3
            else:
                state["streak_cnt"] = 0
        if hit:
            alert = _candidate(
                rule_type="spatial_outlier", level=hit, slot=target_hour, grain=GRANULARITY_HOUR,
                station_id=station_id, station_name=station_name, pollutant="PM2.5",
                value=value, detail=detail,
            )
            outcome.candidates.append(alert)
    return outcome
