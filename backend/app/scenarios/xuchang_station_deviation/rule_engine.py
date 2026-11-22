"""浓度告警规则引擎（判据修订版）。

实现《空气质量浓度数据告警规则体系（判据修订）》规则总表：

- 单点突升 DS：当前值 − 基线 >= MAX(基线 × 比例, 绝对增量)；单窗口成立，
  前提是邻站未同向，且当前浓度高于同组其余站点剔除极值后的均值
  （需求方补充，2026-11-13；对照站不足 3 个时该条件不启用）；
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
from statistics import mean, median
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
        "ol_history": [],
        "ol_chronic_active": False,
        "ol_chronic_reference_delta": None,
        "ol_chronic_since": None,
        "ol_last_hit_day": None,
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
    """单条记录的参数有效值：缺测/负值/带质控标记均视为空值。

    质控标记对分钟表与小时表同等有效（2026-11-13 望田路111号案例：小时表
    标记的零值曾进入 DS 基线造成伪告警），带标记时段不参与基线与判定。
    """
    if has_mark(row.get(f"{column}_mark")):
        return None
    return as_float(row.get(column))


def ge1(value: float, threshold: float) -> bool:
    """数值比较统一约定：保留 1 位小数后比较。"""
    return round(float(value), 1) >= round(float(threshold), 1)


def gt1(value: float, threshold: float) -> bool:
    """严格大于：保留 1 位小数后比较（与 ge1 同一口径）。"""
    return round(float(value), 1) > round(float(threshold), 1)


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


def trimmed_peer_mean(
    values: dict[str, float],
    station_id: str,
    min_peer_count: int,
) -> float | None:
    """其余有效站剔除极值（去最高/最低）后的均值。

    DS 附加条件（需求方补充，2026-11-13）的对比基准：同槽其余站点浓度
    排序后去掉最高与最低再取均值（5 站对照剩 3 站）。对照站少于
    ``min_peer_count``（下限 3）时无法剔除极值，返回 None 表示条件不启用。
    """
    peers = sorted(value for sid, value in values.items() if sid != station_id)
    if len(peers) < max(int(min_peer_count), 3):
        return None
    return mean(peers[1:-1])


def rule_ds(
    value: float,
    baseline_value: float | None,
    pollutant: str,
    level_name: str | None,
    config: AirAlertRuleConfig,
    peer_same_direction_count: int = 0,
    peer_trimmed_mean: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """单点突升：Δ >= MAX(基线 × 比例, 绝对增量)，单窗口成立。

    附加条件（需求方补充，2026-11-13）：本站告警时段浓度需严格高于同组
    其余站点剔除极值后的均值（``peer_trimmed_mean``）；该值为 None 时
    （对照站不足）条件不启用。
    """
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
        "peer_trimmed_mean": round(peer_trimmed_mean, 3) if peer_trimmed_mean is not None else None,
        "recovery_threshold": round(threshold, 3),
    }
    if peer_same_direction_count >= config.neighbor_same_direction_count:
        detail["suppressed_reason"] = "neighbor_same_direction"
        return 0, detail
    if peer_trimmed_mean is not None and not gt1(value, peer_trimmed_mean):
        detail["suppressed_reason"] = "peer_trimmed_mean_not_exceeded"
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
    baseline_value: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """站点离群：本站 vs 其余有效站同刻平均值，且本站自身需未回落。"""
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
        "baseline": round(baseline_value, 3) if baseline_value is not None else None,
        "recovery_threshold": round(threshold, 3),
    }
    # 邻站下降会把同刻均值压低，形成本站“被动离群”；本站未较自身基线
    # 上升时不累计 OL 连续窗口，避免把区域改善误报为目标站异常升高。
    if baseline_value is not None and value <= baseline_value:
        detail["suppressed_reason"] = "target_not_rising"
        state["streak_cnt"] = 0
        return 0, detail
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


# 区域合并按规则类型取参数与主告警度量：CL 比累计抬升绝对量，DS 比相对
# 基线的跳变增量（detail.delta）。
_REGION_MERGE_SPECS: dict[str, tuple[str, str]] = {
    "continuous_rise": ("cl_region_merge_sites", "total_rise_abs"),
    "sudden_rise": ("ds_region_merge_sites", "delta"),
}


def merge_regional_rises(
    candidates: list[dict[str, Any]],
    config: AirAlertRuleConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """区域合并：同污染物同窗口多站命中同一规则时只推最大站一条。

    - 连续抬升 CL：>= ``cl_region_merge_sites`` 站命中 → 只留累计抬升绝对量
      最大的站点；
    - 单点突升 DS：>= ``ds_region_merge_sites`` 站同窗口命中 → 只留跳变增量
      最大的站点。默认 2 收口"恰好两站双命中"缝隙（此时彼此的邻站同向
      抑制都不到门槛，会推出两条互相矛盾的单点突升）；>=3 站命中时引擎层
      已按区域同向抑制、不会产生候选。

    主告警 detail 附全站清单 ``region_stations``；其余站点候选原样返回，
    由推送链以 ``regional_merge`` 抑制入库（不推送但保留流水）。OL 不合并。
    """
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for alert in candidates:
        rule_type = str(alert.get("rule_type") or "")
        if rule_type not in _REGION_MERGE_SPECS:
            kept.append(alert)
            continue
        grouped[
            (
                rule_type,
                str(alert.get("measurement_granularity")),
                str(alert.get("target_pollutant")),
            )
        ].append(alert)
    for (rule_type, _grain, _pollutant), items in grouped.items():
        field_name, metric = _REGION_MERGE_SPECS[rule_type]
        min_sites = int(getattr(config, field_name, 0) or 0)
        if min_sites <= 0 or len(items) < min_sites:
            kept.extend(items)
            continue

        def _metric_value(alert: dict[str, Any]) -> float:
            detail = alert.get("detail") or {}
            raw = alert.get(metric, detail.get(metric))
            try:
                return float(raw or 0)
            except (TypeError, ValueError):
                return 0.0

        primary = max(items, key=_metric_value)
        stations = []
        for item in sorted(items, key=lambda a: str(a.get("station_id"))):
            if item is primary:
                continue
            detail = item.get("detail") or {}
            entry: dict[str, Any] = {
                "station_id": item.get("station_id"),
                "station_name": item.get("station_name"),
                "station_value": item.get("station_value"),
                "air_quality_level": item.get("air_quality_level"),
            }
            if rule_type == "continuous_rise":
                entry["total_rise_abs"] = detail.get("total_rise_abs")
            else:
                entry["delta"] = detail.get("delta")
                entry["baseline"] = detail.get("baseline")
            stations.append(entry)
        primary["detail"]["region_stations"] = stations
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


def modified_z_score(values: dict[str, float], station_id: str) -> float:
    """单站 modified z-score（Iglewicz–Hoaglin，基于六站中位数与 MAD）。

    区分"统计意义上的孤立离群"（wz >= 3.5）与"分布整体分散/双簇"（wz 小）；
    MAD=0（其余站同值）时任何偏离视为极端（inf）。
    """
    med = median(values.values())
    mad = median(sorted(abs(v - med) for v in values.values()))
    x = values[station_id]
    if mad == 0:
        return float("inf") if x != med else 0.0
    return 0.6745 * (x - med) / mad


def evaluate_multi_station_rise(
    outcome: CycleOutcome,
    *,
    grain: str,
    slot: datetime,
    pollutant: str,
    values: dict[str, float],
    levels: dict[tuple[str, str], str],
    ds_context: dict[str, dict[str, Any]],
    series_by_station: dict[str, list[tuple[datetime, float]]],
    names: dict[str, str],
    config: AirAlertRuleConfig,
    cl_context: dict[str, dict[str, Any]] | None = None,
) -> None:
    """多站同步抬升（MR）：双站缝隙与片区一致偏好的正向告警（优先级最高）。

    路径 A（co_rise，时间维度）：同槽 >=mr_min_sites 站各自较自身基线的抬升
    达 mr_amplitude_ratio×DS 阈值（跳变型）或 CL 窗口累计抬升达
    mr_amplitude_ratio×CL 阈值（渐升型，2026-11-22 定版）且过绝对下限；
    反弹守卫拦截低洼基线的微反弹。
    路径 B（co_deviation，空间维度）：OL 触发站 wz<mr_wz_max 且存在同向伴生站。
    触发后覆盖涉事站点的单站 DS/CL/OL 候选（进 region_merged 抑制流水，指回
    MR 事件）；全部涉事站为优档且主站幅度不足全阈值时降级 digest。
    """
    if not config.mr_enabled:
        return
    cap = (config.mr_plausibility_cap or {}).get(pollutant)
    if cap and any(v > float(cap) for v in values.values()):
        return  # 平台数据故障形态（多站同刻超物理上限），不判 MR
    if len(values) < max(int(config.mr_min_sites), 2):
        return
    med_all = median(values.values())

    def _level(sid: str) -> str | None:
        return levels.get((sid, pollutant))

    def _ol_threshold(sid: str) -> float | None:
        level = _level(sid)
        if level is None:
            return None
        peers = {k: x for k, x in values.items() if k != sid}
        if not peers:
            return None
        ratio, absolute = config.thresholds(pollutant, "spatial_outlier", level)
        return max(mean(peers.values()) * ratio, absolute)

    def _ol_delta(sid: str) -> float:
        peers = {k: x for k, x in values.items() if k != sid}
        return values[sid] - mean(peers.values())

    involved: dict[str, dict[str, Any]] = {}
    path: str | None = None
    wz_map: dict[str, float] = {}

    # ---- 路径 A：共升（对各站 DS 上下文放宽到 amplitude_ratio）----
    passed: dict[str, dict[str, Any]] = {}
    for sid in sorted(values):
        ctx = ds_context.get(sid)
        if not ctx:
            continue
        level = ctx.get("level")
        base = float(ctx["baseline"])
        rise = float(ctx["delta"])
        if rise <= 0 or level is None:
            continue
        ratio, absolute = config.thresholds(pollutant, "sudden_rise", level)
        threshold = max(base * ratio, absolute)
        floor = float((config.mr_absolute_floor or {}).get(pollutant, 0.0))
        admission = (
            "ds"
            if rise >= max(float(config.mr_amplitude_ratio) * threshold, floor)
            else None
        )
        if admission is None:
            # 渐升型共升（2026-11-22 定版）：CL 窗口累计抬升达
            # amplitude_ratio×CL 阈值亦可入站。3 小时爬坡的站末跳普遍不足
            # DS 半阈值，仅按单小时口径收站会漏掉区域性同步抬升。
            cl = (cl_context or {}).get(sid)
            if cl:
                cl_ratio, cl_absolute = config.thresholds(pollutant, "continuous_rise", level)
                cl_threshold = max(float(cl["baseline"]) * cl_ratio, cl_absolute)
                cl_rise = float(cl["rise"])
                if cl_rise > 0 and cl_rise >= max(
                    float(config.mr_amplitude_ratio) * cl_threshold, floor
                ):
                    admission = "cl"
                    base = float(cl["baseline"])
                    rise = cl_rise
                    threshold = cl_threshold
        if admission is None:
            continue
        history = [v for t, v in (series_by_station.get(sid) or []) if t < slot]
        pct = (100.0 * sum(1 for v in history if v <= base) / len(history)) if history else 50.0
        if pct < float(config.mr_rebound_pct) and not (values[sid] >= med_all or rise >= threshold):
            continue  # 反弹守卫：低洼基线的微反弹不构成"同步抬升"
        passed[sid] = {
            "station_id": sid, "station_name": names.get(sid, sid), "station_value": values[sid],
            "baseline": round(base, 3), "rise": round(rise, 3),
            "threshold": round(threshold, 3), "baseline_day_percentile": round(pct),
            "air_quality_level": level, "admission": admission,
        }
    if len(passed) >= int(config.mr_min_sites):
        path, involved = "co_rise", passed

    # ---- 路径 B：共偏（OL 触发站 wz 有效 + 同向伴生）----
    if path is None:
        for sid in sorted(values):
            thr = _ol_threshold(sid)
            if thr is None:
                continue
            delta = _ol_delta(sid)
            if delta <= 0 or delta < thr:
                continue
            wz = modified_z_score(values, sid)
            wz_map[sid] = wz
            if wz >= float(config.mr_wz_max):
                continue  # 统计意义上的孤立离群 → 交给 OL 单站告警
            companions = []
            for pid in sorted(values):
                if pid == sid:
                    continue
                thr_p = _ol_threshold(pid)
                if thr_p is None:
                    continue
                delta_p = _ol_delta(pid)
                if delta_p > 0 and delta_p >= float(config.mr_companion_ratio) * thr_p:
                    companions.append(pid)
            if not companions:
                continue
            path = "co_deviation"
            involved[sid] = {
                "station_id": sid, "station_name": names.get(sid, sid), "station_value": values[sid],
                "peer_mean": round(mean({k: x for k, x in values.items() if k != sid}.values()), 3),
                "delta": round(delta, 3), "threshold": round(thr, 3),
                "modified_z_score": round(wz, 2) if wz != float("inf") else None,
                "air_quality_level": _level(sid),
            }
            for pid in companions:
                thr_p = _ol_threshold(pid)
                involved[pid] = {
                    "station_id": pid, "station_name": names.get(pid, pid), "station_value": values[pid],
                    "peer_mean": round(mean({k: x for k, x in values.items() if k != pid}.values()), 3),
                    "delta": round(_ol_delta(pid), 3), "threshold": round(thr_p, 3),
                    "air_quality_level": _level(pid),
                }
            break
    if path is None or not involved:
        return

    def _amplitude(entry: dict[str, Any]) -> float:
        threshold = float(entry.get("threshold") or 0)
        gained = float(entry.get("rise") if "rise" in entry else entry.get("delta") or 0)
        return (gained / threshold) if threshold > 0 else 0.0

    primary_sid = max(sorted(involved), key=lambda s: (_amplitude(involved[s]), s))
    primary = involved[primary_sid]
    # 低基线反弹不报送（2026-11-20 需求方定版）：主站基线处当日低分位时，
    # 幅度比会被绝对门槛在低基线上放大（如 5→14 相对阈值 6 达 1.5×），
    # 属低谷回升而非真实抬升 → digest（不推送，流水与日摘要可审计）。
    # 真实抬升会在后续槽（基线回升后、分位脱离低洼区）正常推送。
    primary_rebound = (
        path == "co_rise"
        and float(primary.get("baseline_day_percentile") or 50.0) < float(config.mr_rebound_pct)
    )
    all_excellent = all(entry.get("air_quality_level") == "优" for entry in involved.values())
    tier = "digest" if all_excellent and _amplitude(primary) < 1.0 else "push"
    if primary_rebound:
        tier = "digest"

    others = [involved[s] for s in sorted(involved) if s != primary_sid]
    detail: dict[str, Any] = {
        "path": path,
        "involved_stations": [involved[s] for s in sorted(involved)],
        "region_stations": others,
        "primary_amplitude": round(_amplitude(primary), 3),
        "mr_tier": tier,
        "threshold": float(primary.get("threshold") or 0),
        "wz": (
            {names.get(k, k): (None if wz_map[k] == float("inf") else round(wz_map[k], 2)) for k in sorted(wz_map)}
            or None
        ),
        "recovery_threshold": float(primary.get("threshold") or 0),
    }
    candidate = _candidate(
        rule_type="multi_station_rise", slot=slot, grain=grain,
        station_id=primary_sid, station_name=names.get(primary_sid),
        pollutant=pollutant, value=float(primary["station_value"]),
        level_name=primary["air_quality_level"], detail=detail,
    )
    outcome.candidates.append(candidate)
    outcome.recovery_metrics[(grain, primary_sid, pollutant, "multi_station_rise")] = float(
        primary.get("rise") if "rise" in primary else primary.get("delta") or 0
    )

    # 覆盖涉事站点的单站候选（共偏路径不覆盖 CL：CL 是时间维度抬升）。
    covered_rules = {"sudden_rise", "spatial_outlier"} | ({"continuous_rise"} if path == "co_rise" else set())
    kept: list[dict[str, Any]] = []
    for alert in outcome.candidates:
        if (
            alert.get("station_id") in involved
            and alert.get("target_pollutant") == pollutant
            and str(alert.get("rule_type")) in covered_rules
        ):
            alert["merged_into_event_id"] = candidate["event_id"]
            outcome.region_merged.append(alert)
        else:
            kept.append(alert)
    outcome.candidates = kept


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
    mr_snapshots: list[dict[str, Any]] = []

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
        cl_context: dict[str, dict[str, Any]] = {}
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
                    value, context["baseline"], pollutant, level, config, peer_same_direction,
                    peer_trimmed_mean=trimmed_peer_mean(all_values, station_id, config.ds_peer_trim_min_peers),
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
                cl_context[station_id] = {"baseline": baseline, "rise": value - baseline}
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
                    baseline_value=context["baseline"] if context is not None else None,
                )
                if hit:
                    detail["peer_station_count"] = peer_count
                    outcome.candidates.append(_candidate(
                        rule_type="spatial_outlier", slot=target_slot, grain=grain,
                        station_id=station_id, station_name=station_name, pollutant=pollutant,
                        value=value, level_name=level, detail=detail,
                    ))

        _reset_missing_streaks(states, grain, pollutant, set(current))
        mr_snapshots.append({
            "pollutant": pollutant,
            "values": all_values,
            "ds_context": ds_context,
            "cl_context": cl_context,
            "series": series_by_station,
            "names": {
                sid: (row.get("name") or row.get("station_name") or sid)
                for sid, (_value, row) in current.items()
            },
        })

    for snapshot in mr_snapshots:
        evaluate_multi_station_rise(
            outcome, grain=grain, slot=target_slot, pollutant=snapshot["pollutant"],
            values=snapshot["values"], levels=levels, ds_context=snapshot["ds_context"],
            cl_context=snapshot["cl_context"],
            series_by_station=snapshot["series"], names=snapshot["names"], config=config,
        )
    mr_covered = outcome.region_merged  # MR 覆盖的单站候选（merge 只返回 CL 合并抑制）
    outcome.candidates, suppressed = merge_regional_rises(outcome.candidates, config)
    outcome.region_merged = mr_covered + suppressed
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
    mr_snapshots: list[dict[str, Any]] = []
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
    cl_context: dict[str, dict[str, Any]] = {}
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
                value, context["baseline"], pollutant, level, config, peer_same_direction,
                peer_trimmed_mean=trimmed_peer_mean(all_values, station_id, config.ds_peer_trim_min_peers),
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
            cl_context[station_id] = {"baseline": baseline, "rise": value - baseline}
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
                baseline_value=context["baseline"] if context is not None else None,
            )
            if hit:
                detail["peer_station_count"] = peer_count
                outcome.candidates.append(_candidate(
                    rule_type="spatial_outlier", slot=target_hour, grain=grain,
                    station_id=station_id, station_name=station_name, pollutant=pollutant,
                    value=value, level_name=level, detail=detail,
                ))

    _reset_missing_streaks(states, grain, pollutant, set(current))
    mr_snapshots.append({
        "pollutant": pollutant,
        "values": all_values,
        "ds_context": ds_context,
        "cl_context": cl_context,
        "series": series_by_station,
        "names": {
            sid: (row.get("name") or row.get("station_name") or sid)
            for sid, (_value, row) in current.items()
        },
    })
    for snapshot in mr_snapshots:
        evaluate_multi_station_rise(
            outcome, grain=grain, slot=target_hour, pollutant=snapshot["pollutant"],
            values=snapshot["values"], levels=levels, ds_context=snapshot["ds_context"],
            cl_context=snapshot["cl_context"],
            series_by_station=snapshot["series"], names=snapshot["names"], config=config,
        )
    mr_covered = outcome.region_merged  # MR 覆盖的单站候选（merge 只返回 CL 合并抑制）
    outcome.candidates, suppressed = merge_regional_rises(outcome.candidates, config)
    outcome.region_merged = mr_covered + suppressed
    return outcome
