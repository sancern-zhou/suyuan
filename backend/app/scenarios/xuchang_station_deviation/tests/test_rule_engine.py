"""浓度告警规则引擎测试（判据修订版）。

对应《空气质量浓度数据告警规则体系（判据修订）》：DS 单点突升、
CL 连续抬升、OL 站点离群；选档按站点 × 污染物 1h IAQI；
O3 不判、限值突破不保留、无告警级别。

时间线均使用 Asia/Shanghai 时区的 5 分钟槽/整点槽；行数据用中大表字段
形态（``_mark`` 列表示质控标记，缺测/负值视为无效）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.scenarios.xuchang_station_deviation.push_control import (
    AlertStateStore,
    PushLogStore,
    apply_push_chain,
)
from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig
from app.scenarios.xuchang_station_deviation.rule_engine import (
    evaluate_five_minute_cycle,
    evaluate_pm25_hourly_cycle,
    level_name_for,
    new_rule_state,
)

TZ = ZoneInfo("Asia/Shanghai")
STATIONS = ("a", "b", "c", "d", "e", "f")


def _row(station_id: str, data_time: datetime, values: dict[str, Any] | None = None,
         marks: dict[str, str] | None = None, source: str = "minute") -> dict[str, Any]:
    row: dict[str, Any] = {
        "station_id": station_id, "name": station_id, "data_source": source,
        "data_time": data_time, "pm25": None, "pm10": None, "so2": None,
        "no2": None, "co": None, "o3": None,
    }
    row.update(values or {})
    for column, mark in (marks or {}).items():
        row[f"{column}_mark"] = mark
    return row


class MemStates:
    """内存版 alert_state 存储（接口与 AlertStateStore 一致）。"""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def instance(self, grain: str, station: str, pollutant: str, rule: str) -> dict[str, Any]:
        return self._states.setdefault((grain, station, pollutant, rule), new_rule_state())

    def iterate(self, grain: str, pollutant: str) -> list[tuple[str, str, dict[str, Any]]]:
        return [
            (key[1], key[3], state)
            for key, state in self._states.items()
            if key[0] == grain and key[2] == pollutant
        ]


def _history_rows(station_id: str, values: list[float], slot: datetime,
                  column: str = "pm10", skip_slots: set[int] | None = None,
                  marks: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """生成 slot 之前 N 个 5 分钟槽的历史行。"""
    rows = []
    for index, value in enumerate(values):
        if skip_slots and index in skip_slots:
            continue
        marks_for_row = {column: marks[index]} if marks and index in marks else None
        rows.append(_row(
            station_id, slot - timedelta(minutes=5 * (len(values) - index)),
            {column: value}, marks_for_row,
        ))
    return rows


def _cycle(rows: list[dict[str, Any]], slot: datetime,
           config: AirAlertRuleConfig | None = None, states: MemStates | None = None):
    return evaluate_five_minute_cycle(
        rows, target_slot=slot, config=config or AirAlertRuleConfig(),
        states=states or MemStates(),
    )


def _slot_values(outcome, rule_type: str | None = None) -> list[dict[str, Any]]:
    return [c for c in outcome.candidates if rule_type is None or c["rule_type"] == rule_type]


def _hour_rows(values: list[tuple[datetime, float]], station_id: str, column: str = "pm25") -> list[dict[str, Any]]:
    return [_row(station_id, moment, {column: value}, source="hour") for moment, value in values]


# ---- 选档（站点 × 污染物 1h IAQI）----

def test_level_name_for_uses_hj633_breakpoints():
    # PM2.5/PM10 用日平均断点（2026 过渡限值：良上限 60/120）；SO2 用 1h 断点
    #（良下限 150）。
    assert level_name_for("PM2.5", 55) == "良"
    assert level_name_for("PM2.5", 65) == "轻度污染"
    assert level_name_for("PM2.5", 30) == "优"
    assert level_name_for("PM10", 110) == "良"
    assert level_name_for("PM10", 130) == "轻度污染"
    assert level_name_for("SO2", 160) == "良"
    assert level_name_for("SO2", 100) == "优"
    assert level_name_for("CO", 6) == "良"


# ---- DS 单点突升 ----

def _ds_scenario(slot: datetime, current: float, base_value: float = 40.0,
                 others: float = 40.0, level_hour_value: float = 60.0,
                 states: MemStates | None = None):
    """构造良档（小时 60 → PM10 良）下基线 3 期的 DS 场景。"""
    rows = []
    for sid in STATIONS:
        hour_value = level_hour_value if sid == "a" else others
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": hour_value}, source="hour"))
        rows.extend(_history_rows(sid, [base_value] * 4, slot))
    for sid in STATIONS:
        value = current if sid == "a" else others
        rows.append(_row(sid, slot, {"pm10": value}))
    outcome = _cycle(rows, slot, states=states or MemStates())
    return outcome


def test_ds_hits_when_both_gates_pass():
    # 良档：阈值 = max(40×0.3, 15) = 15。55−40=15 → 触发，单窗口即成立。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome = _ds_scenario(slot, current=55.0)
    rises = _slot_values(outcome, "sudden_rise")
    assert len(rises) == 1 and rises[0]["station_id"] == "a"
    assert rises[0]["air_quality_level"] == "良"
    assert rises[0]["detail"]["threshold"] == 15.0
    assert rises[0]["detail"]["delta"] == 15.0


def test_ds_absolute_gate_dominates_low_baseline():
    # 基线 30、轻度档（小时 130 → PM10 轻度）：阈值 = max(30×0.25, 20) = 20。
    # Δ15（45−30）< 20 → 不触发；Δ20（50−30）→ 触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 130.0 if sid == "a" else 30.0}, source="hour"))
        rows.extend(_history_rows(sid, [30.0] * 4, slot))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": 45.0 if sid == "a" else 30.0}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "sudden_rise") == []
    slot2 = slot + timedelta(minutes=5)
    rows2 = []
    for sid in STATIONS:
        rows2.append(_row(sid, slot2 - timedelta(hours=1), {"pm10": 130.0 if sid == "a" else 30.0}, source="hour"))
        rows2.extend(_history_rows(sid, [30.0] * 5, slot2))
    for sid in STATIONS:
        rows2.append(_row(sid, slot2, {"pm10": 50.0 if sid == "a" else 30.0}))
    outcome2 = _cycle(rows2, slot2)
    assert len(_slot_values(outcome2, "sudden_rise")) == 1


def test_ds_suppressed_when_neighbors_rise_too():
    # 邻站同向：≥2 个邻站也命中各自 DS 阈值 → 区域过程，不判单点突升。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
    current = {"a": 60.0, "b": 60.0, "c": 60.0, "d": 40.0, "e": 40.0, "f": 40.0}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": current[sid]}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "sudden_rise") == []


def test_ds_single_station_still_fires_with_two_neighbors_flat():
    # 只有本站命中、邻站持平 → 单点突升成立。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome = _ds_scenario(slot, current=60.0)
    assert len(_slot_values(outcome, "sudden_rise")) == 1


def test_ds_needs_three_consecutive_history_slots():
    # 历史槽不足 3 个连续 → 基线缺失，不判 DS。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 2, slot))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": 60.0 if sid == "a" else 40.0}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "sudden_rise") == []


def test_o3_is_not_evaluated():
    # O3 暂不纳入：任何浓度都不产生 O3 告警。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"o3": 100.0}, source="hour"))
        rows.extend(_history_rows(sid, [100.0] * 4, slot, column="o3"))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"o3": 300.0 if sid == "a" else 100.0}))
    outcome = _cycle(rows, slot)
    assert outcome.candidates == []


# ---- CL 连续抬升 ----

def _cl_run(series: list[float], level_hour_value: float = 60.0):
    """构造良档场景逐槽跑，返回累计的 CL 候选。

    series 为抬升段起点后的值序列；首值即抬升起点，之前自动垫 3 个基线槽
    （值与首值相同）。邻站全部持平 40。
    """
    slot0 = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    states = MemStates()
    candidates: list[dict[str, Any]] = []
    baseline_pad = [series[0]] * 3
    full = baseline_pad + list(series)
    for index in range(len(full)):
        slot = slot0 + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": level_hour_value}, source="hour"))
            history = full[:index] if sid == "a" else [40.0] * index
            rows.extend(_history_rows(sid, history, slot))
            value = full[index] if sid == "a" else 40.0
            rows.append(_row(sid, slot, {"pm10": value}))
        outcome = _cycle(rows, slot, states=states)
        candidates.extend(_slot_values(outcome, "continuous_rise"))
    return candidates


def test_cl_three_monotonic_segments_with_even_share():
    # 良档：基线 40、段增量 5/5/5、累计 15 < max(40×0.5, 25)=25 → 不触发；
    # 段增量 10/10/10、累计 30 ≥ 25、各段 10 ≥ 4.5 → 触发。
    assert _cl_run([40.0, 45.0, 50.0, 55.0]) == []
    candidates = _cl_run([40.0, 50.0, 60.0, 70.0])
    assert len(candidates) == 1
    alert = candidates[0]
    assert alert["air_quality_level"] == "良"
    assert alert["detail"]["total_rise_abs"] == 30.0
    assert alert["detail"]["segment_gains"] == [10.0, 10.0, 10.0]


def test_cl_rejects_uneven_segments():
    # 单尖峰形态：40→70→70→70。段增量 30/0/0，0 < 30×0.15 → 不判 CL。
    assert _cl_run([40.0, 70.0, 70.0, 70.0]) == []


def test_cl_rejects_dip_in_window():
    # 中途回落：40→55→50→70。有负段 → 不判 CL。
    assert _cl_run([40.0, 55.0, 50.0, 70.0]) == []


def test_cl_baseline_is_before_start_not_sliding():
    # 基线固定为抬升起点前 15 分钟均值（40），不随窗口滑动：
    # 段增量 15/5/5、累计 25 ≥ 25、各段 ≥ 3.75 → 触发。
    candidates = _cl_run([40.0, 55.0, 60.0, 65.0])
    assert len(candidates) == 1
    assert candidates[0]["detail"]["baseline"] == 40.0


def test_cl_needs_consecutive_slots():
    # 缺一个槽 → 窗口不连续，不判 CL。
    slot0 = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot0 - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [40.0, 40.0, 40.0, 40.0], slot0, skip_slots={2}))
    for sid in STATIONS:
        rows.append(_row(sid, slot0, {"pm10": 70.0 if sid == "a" else 40.0}))
    outcome = _cycle(rows, slot0)
    assert _slot_values(outcome, "continuous_rise") == []


def test_marked_current_value_is_invalid():
    # 质控标记：带标记的当前值不参与判定。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
    for sid in STATIONS:
        marks = {"pm10": "质控"} if sid == "a" else None
        rows.append(_row(sid, slot, {"pm10": 200 if sid == "a" else 40.0}, marks=marks))
    outcome = _cycle(rows, slot)
    assert ("5min", "a", "PM10") not in outcome.current_values
    assert all(c["station_id"] != "a" for c in outcome.candidates)


# ---- OL 站点离群 ----

def _ol_rows(slot: datetime, current: dict[str, float], pollutant: str = "no2"):
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {pollutant: 55.0}, source="hour"))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {pollutant: current[sid]}))
    return rows


def test_ol_no_alert_level_field():
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = _ol_rows(slot, {"a": 96.0, "b": 55.0, "c": 55.0, "d": 55.0, "e": 55.0, "f": 55.0})
    outcome = _cycle(rows, slot)
    assert all("alert_level" not in c for c in outcome.candidates)


def test_ol_uses_regional_mean_not_trimmed_mean():
    # 其余站 55/55/55/55/200：简单平均 = 84（旧去极值口径会剔掉 200 得 55）。
    # Δ12 < max(84×0.5, 20) → 不触发（若用旧口径 96−55=41 ≥ 27.5+ 会误触发）。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = _ol_rows(slot, {"a": 96.0, "b": 55.0, "c": 55.0, "d": 55.0, "e": 55.0, "f": 200.0})
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "spatial_outlier") == []


def test_ol_requires_two_windows_for_five_min():
    # 5 分钟 OL 需连续 2 个窗口：第 1 窗口只记 streak，第 2 窗口触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    current = {"a": 150.0, "b": 40.0, "c": 40.0, "d": 40.0, "e": 40.0, "f": 40.0}
    states = MemStates()
    rows1 = _ol_rows(slot, current, "pm10")
    outcome1 = _cycle(rows1, slot, states=states)
    assert _slot_values(outcome1, "spatial_outlier") == []
    slot2 = slot + timedelta(minutes=5)
    rows2 = _ol_rows(slot2, current, "pm10")
    outcome2 = _cycle(rows2, slot2, states=states)
    outliers = _slot_values(outcome2, "spatial_outlier")
    assert len(outliers) == 1 and outliers[0]["station_id"] == "a"
    assert outliers[0]["detail"]["hold_streak"] == 2


def test_ol_requires_min_region_stations():
    # 有效站 <4：不判 OL。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = [_row(sid, slot, {"pm10": 150.0 if sid == "a" else 40.0}) for sid in STATIONS[:3]]
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "spatial_outlier") == []


def test_ol_streak_resets_after_interruption():
    # 中途一窗不满足 → streak 清零，重新累计 2 窗口才触发。
    slot0 = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    states = MemStates()
    up = {"a": 150.0, "b": 40.0, "c": 40.0, "d": 40.0, "e": 40.0, "f": 40.0}
    down = {**up, "a": 40.0}
    _cycle(_ol_rows(slot0, up, "pm10"), slot0, states=states)
    slot1 = slot0 + timedelta(minutes=5)
    _cycle(_ol_rows(slot1, down, "pm10"), slot1, states=states)
    slot2 = slot1 + timedelta(minutes=5)
    outcome2 = _cycle(_ol_rows(slot2, up, "pm10"), slot2, states=states)
    assert _slot_values(outcome2, "spatial_outlier") == []
    slot3 = slot2 + timedelta(minutes=5)
    outcome3 = _cycle(_ol_rows(slot3, up, "pm10"), slot3, states=states)
    assert len(_slot_values(outcome3, "spatial_outlier")) == 1


def test_ol_recovery_metric_uses_deviation_not_concentration():
    # 恢复防抖必须与 OL 阈值同口径（本站−其余均值偏差），不能用原始浓度：
    # 1003A 案例里浓度 64~68 恒大于偏差阈值 20，用浓度比较永远无法恢复。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    current = {"a": 64.0, "b": 68.0, "c": 42.0, "d": 42.0, "e": 38.0, "f": 46.0}
    outcome = _cycle(_ol_rows(slot, current, "pm10"), slot)
    peer_mean = (68.0 + 42.0 + 42.0 + 38.0 + 46.0) / 5
    metric = outcome.recovery_metrics[("5min", "a", "PM10", "spatial_outlier")]
    assert metric == pytest.approx(64.0 - peer_mean)
    assert metric < 20.0
    # 原始浓度仍保留在 current_values 供展示。
    assert outcome.current_values[("5min", "a", "PM10")] == 64.0


# ---- PM2.5 小时版 ----

def test_pm25_hourly_ds_and_level_from_same_hour():
    # 小时值 65 定档为轻度（良上限 60）；轻度 DS 阈值 = max(50×0.25, 10)=12.5；
    # 65−50=15 ≥ 12.5 → 触发。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, hour - timedelta(hours=1), {"pm25": 50.0 if sid == "a" else 40.0}, source="hour"))
        rows.append(_row(sid, hour, {"pm25": 65.0 if sid == "a" else 40.0}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    rises = [c for c in outcome.candidates if c["rule_type"] == "sudden_rise"]
    assert len(rises) == 1
    assert rises[0]["air_quality_level"] == "轻度污染"
    assert rises[0]["detail"]["threshold"] == 12.5
    assert rises[0]["measurement_granularity"] == "hour"


def test_pm25_hourly_ds_suppressed_when_region_rises():
    # 全站同步从 40 → 55：邻站同向（≥2 个命中）→ 不判 DS。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, hour - timedelta(hours=1), {"pm25": 40.0}, source="hour"))
        rows.append(_row(sid, hour, {"pm25": 55.0}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert [c for c in outcome.candidates if c["rule_type"] == "sudden_rise"] == []


def test_pm25_hourly_cl_three_hours():
    # 连续 3 小时上涨 40→55→65→75，基线取起点前一小时 40：
    # 累计 35 ≥ max(40×0.5, 25)=25，各段 15/10/10 ≥ 5.25 → 触发。
    hour0 = datetime(2026, 9, 12, 6, 0, tzinfo=TZ)
    series = [40.0, 55.0, 65.0, 75.0]
    rows = []
    for sid in STATIONS:
        rows.extend(_hour_rows(
            [(hour0 + timedelta(hours=i), series[i] if sid == "a" else 40.0) for i in range(4)],
            sid,
        ))
    states = MemStates()
    rises: list[dict[str, Any]] = []
    for index in range(len(series)):
        target = hour0 + timedelta(hours=index)
        outcome = evaluate_pm25_hourly_cycle(
            rows, target_hour=target, config=AirAlertRuleConfig(), states=states,
        )
        rises.extend(c for c in outcome.candidates if c["rule_type"] == "continuous_rise")
    assert len(rises) == 1
    assert rises[0]["detail"]["total_rise_abs"] == 35.0
    assert rises[0]["detail"]["segment_gains"] == [15.0, 10.0, 10.0]


def test_pm25_hourly_ol_single_window():
    # PM2.5 OL 单窗口即成立：本站 65、其余 40（轻度档阈值 max(40×0.35, 18)=18）。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, hour, {"pm25": 65.0 if sid == "a" else 40.0}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    outliers = [c for c in outcome.candidates if c["rule_type"] == "spatial_outlier"]
    assert len(outliers) == 1 and outliers[0]["station_id"] == "a"


# ---- CL 区域合并（>=4 站同因子同窗口命中 → 最大站主告警 + 全站清单）----

def _regional_cl_run(rising: dict[str, float], config: AirAlertRuleConfig | None = None):
    """6 站 CL 区域场景：前 3 个槽全部 40（基线垫底），后 4 个槽按
    series_map 逐站抬升（40→50→60→rising[sid]）。"""
    slot0 = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    full = {sid: [40.0, 40.0, 40.0, 40.0, 50.0, 60.0, rising[sid]] for sid in STATIONS}
    states = MemStates()
    outcome = None
    for index in range(len(full["a"])):
        slot = slot0 + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 60.0}, source="hour"))
            rows.extend(_history_rows(sid, full[sid][:index], slot))
            rows.append(_row(sid, slot, {"pm10": full[sid][index]}))
        outcome = _cycle(rows, slot, config=config, states=states)
    return outcome


def test_regional_rise_merged_to_single_primary():
    # 4 个站同时抬升（各段 10、累计 30 ≥ 25）→ 合并为一条，
    # detail.region_stations 带 3 站，其余进 region_merged。
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 70.0, "e": 40.0, "f": 40.0})
    rises = [c for c in outcome.candidates if c["rule_type"] == "continuous_rise"]
    assert len(rises) == 1
    primary = rises[0]
    assert primary["region_merged_count"] == 4
    assert len(primary["detail"]["region_stations"]) == 3
    assert {item["station_id"] for item in primary["detail"]["region_stations"]} == {"b", "c", "d"}
    assert len(outcome.region_merged) == 3
    assert all(item["station_id"] in {"b", "c", "d"} for item in outcome.region_merged)


def test_regional_merge_suppressed_candidates_logged_to_push_log(tmp_path):
    # 被合并站点的通报内容由主告警（region_stations 清单）承载，但流水必须
    # 可审计：reason=regional_merge，且 merged_into_event_id 指回主告警。
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 70.0, "e": 40.0, "f": 40.0})
    primary = next(c for c in outcome.candidates if c["rule_type"] == "continuous_rise")
    pre = []
    for alert in outcome.region_merged:
        alert["suppress_reason"] = "regional_merge"
        alert["merged_into_event_id"] = primary["event_id"]
        pre.append({"alert": alert, "reason": "regional_merge"})
    store = AlertStateStore(tmp_path)
    log_store = PushLogStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=datetime(2026, 9, 12, 8, 40, tzinfo=TZ), log_store=log_store,
        recovery_metrics=outcome.recovery_metrics, pre_suppressed=pre,
    )
    assert len(pushed) == 1 and pushed[0]["event_id"] == primary["event_id"]
    assert [item["reason"] for item in suppressed] == ["regional_merge"] * 3
    log_file = next(iter((tmp_path / "push_log").glob("*.jsonl")))
    entries = [json.loads(line) for line in log_file.read_text(encoding="utf-8").strip().splitlines()]
    merge_entries = [e for e in entries if e["reason"] == "regional_merge"]
    assert len(merge_entries) == 3
    assert all(e["merged_into_event_id"] == primary["event_id"] for e in merge_entries)
    assert {e["station_id"] for e in merge_entries} == {"b", "c", "d"}


def test_regional_rise_not_triggered_below_threshold_sites():
    # 只有 3 个站命中 → 不合并，各自保留候选。
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 40.0, "e": 40.0, "f": 40.0})
    rises = [c for c in outcome.candidates if c["rule_type"] == "continuous_rise"]
    assert len(rises) == 3
    assert outcome.region_merged == []


def test_regional_rise_merge_can_be_disabled():
    # cl_region_merge_sites=0：不合并，6 站全部各自保留。
    outcome = _regional_cl_run(
        {"a": 70.0, "b": 70.0, "c": 70.0, "d": 70.0, "e": 70.0, "f": 70.0},
        config=AirAlertRuleConfig(cl_region_merge_sites=0),
    )
    assert len([c for c in outcome.candidates if c["rule_type"] == "continuous_rise"]) == 6


# ---- 推送链协同（引擎产物 → 管控）----

def test_priority_keeps_sudden_rise_over_outlier(tmp_path):
    # #24：同站同因子同窗口同时命中 DS 与 OL → 只推 DS（优先级 1 < 3）。
    # OL 需连续 2 个窗口，第 2 窗口与 DS 同窗口出现。
    slot0 = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    states = MemStates()
    outcome_all = None
    for index in range(2):
        slot = slot0 + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
            rows.extend(_history_rows(sid, [40.0] * (4 + index), slot))
        current = {"a": 100.0, "b": 40.0, "c": 40.0, "d": 40.0, "e": 40.0, "f": 40.0}
        for sid in STATIONS:
            rows.append(_row(sid, slot, {"pm10": current[sid]}))
        outcome_all = _cycle(rows, slot, states=states)
    types = {c["rule_type"] for c in outcome_all.candidates}
    assert {"sudden_rise", "spatial_outlier"} <= types
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome_all.candidates), store=store, config=AirAlertRuleConfig(),
        now=slot0 + timedelta(minutes=5), log_store=PushLogStore(tmp_path),
        recovery_metrics=outcome_all.recovery_metrics,
    )
    assert [a["rule_type"] for a in pushed] == ["sudden_rise"]
    assert all(item["reason"] == "priority" for item in suppressed)


def test_window_summary_covers_three_stations(tmp_path):
    # 同窗口 3 个站点各一条 DS → 合并为一条摘要。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    candidates = []
    for sid in ("a", "c", "e"):
        candidates.append({
            "event_id": f"e-{sid}", "occurred_at": slot.isoformat(), "city": "许昌市",
            "station_id": sid, "station_name": sid, "target_pollutant": "PM10",
            "measurement_granularity": "5min", "rule_type": "sudden_rise",
            "rule_label": "单点突升", "rule_priority": 1,
            "air_quality_level": "良", "station_value": 55.0,
            "recovery_threshold": 15.0, "detail": {},
        })
    store = AlertStateStore(tmp_path)
    pushed, _suppressed, summary = apply_push_chain(
        candidates, store=store, config=AirAlertRuleConfig(), now=slot,
        log_store=PushLogStore(tmp_path), recovery_metrics={},
    )
    assert len(pushed) == 3
    assert summary is not None and "3 个站点" in summary
    store.save()
