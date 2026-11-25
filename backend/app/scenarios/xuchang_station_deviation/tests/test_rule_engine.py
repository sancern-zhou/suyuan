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
    trimmed_peer_mean,
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


def test_trimmed_peer_mean_removes_extremes():
    # 剔除极值口径：对照站 [40,40,70,70,70] 去最高/最低 → mean(40,70,70)。
    values = {"a": 10.0, "b": 40.0, "c": 40.0, "d": 70.0, "e": 70.0, "f": 70.0}
    assert trimmed_peer_mean(values, "a", 3) == pytest.approx((40.0 + 70.0 + 70.0) / 3)
    # 对照站不足（无法剔除极值）→ None，条件不启用。
    assert trimmed_peer_mean({"a": 10.0, "b": 40.0}, "a", 3) is None
    assert trimmed_peer_mean(values, "a", 99) is None


def test_ds_suppressed_below_peer_trimmed_mean():
    # DS 附加条件：本站浓度需高于同组其余站点剔除极值后的均值。
    # 对照站 [40,40,90,90,90] 去极值均值 = (40+90+90)/3 ≈ 73.3；
    # a 40→55（Δ15 ≥ 良档阈值 15，双门限过、邻站同向 0），但 55 < 73.3 → 抑制。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    base = {"a": 40.0, "b": 90.0, "c": 90.0, "d": 90.0, "e": 40.0, "f": 40.0}
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 60.0 if sid == "a" else base[sid]}, source="hour"))
        rows.extend(_history_rows(sid, [base[sid]] * 4, slot))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": 55.0 if sid == "a" else base[sid]}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "sudden_rise") == []


def test_ds_suppressed_when_equal_to_peer_trimmed_mean():
    # 严格高于才成立：对照站 [40,55,70,40,70] 去极值均值 = (40+55+70)/3 = 55，
    # a=55 等于均值 → 不触发。对照站高值档位抬到中度（阈值 45）避免邻站同向。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    current = {"a": 55.0, "b": 40.0, "c": 55.0, "d": 70.0, "e": 40.0, "f": 70.0}
    rows = []
    for sid in STATIONS:
        level_value = 60.0 if sid == "a" else 300.0
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": level_value}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
        rows.append(_row(sid, slot, {"pm10": current[sid]}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "sudden_rise") == []


def test_ds_skips_trimmed_mean_condition_with_few_peers():
    # 有效站只有 3 个（对照 2 个，无法剔除极值）→ 附加条件不启用，
    # DS 双门限过即触发；detail.peer_trimmed_mean=None 表示未启用。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS[:3]:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 60.0 if sid == "a" else 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
    for sid in STATIONS[:3]:
        rows.append(_row(sid, slot, {"pm10": 55.0 if sid == "a" else 40.0}))
    outcome = _cycle(rows, slot)
    rises = _slot_values(outcome, "sudden_rise")
    assert len(rises) == 1 and rises[0]["station_id"] == "a"
    assert rises[0]["detail"]["peer_trimmed_mean"] is None


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
    assert alert["detail"]["peer_trimmed_mean"] == 40.0


def test_cl_suppressed_below_peer_trimmed_mean():
    # 2026-11-25 08:10 市一中实例：基线 27.333，38→43→48，累计 20.667
    # 达到优档阈值 18，但其余五站去极值均值 65，低于均值不得触发 CL。
    slot = datetime(2026, 11, 25, 8, 10, tzinfo=TZ)
    peers = {"b": 56.0, "c": 72.0, "d": 67.0, "e": 57.0, "f": 73.0}
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 60.0}, source="hour"))
        history = [23.0, 27.0, 32.0, 38.0, 43.0] if sid == "a" else [peers[sid]] * 5
        rows.extend(_history_rows(sid, history, slot))
        rows.append(_row(sid, slot, {"pm10": 48.0 if sid == "a" else peers[sid]}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "continuous_rise") == []


def test_cl_suppressed_when_equal_to_peer_trimmed_mean():
    # 与 DS 相同，必须严格高于：其他站 [40,55,70,40,70] 去极值均值为 55。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    peers = {"b": 40.0, "c": 55.0, "d": 70.0, "e": 40.0, "f": 70.0}
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 30.0}, source="hour"))
        history = [20.0, 20.0, 20.0, 30.0, 40.0] if sid == "a" else [peers[sid]] * 5
        rows.extend(_history_rows(sid, history, slot))
        rows.append(_row(sid, slot, {"pm10": 55.0 if sid == "a" else peers[sid]}))
    outcome = _cycle(rows, slot)
    assert _slot_values(outcome, "continuous_rise") == []


def test_cl_skips_trimmed_mean_condition_with_few_peers():
    # 只有 2 个有效对照站时无法去最高/最低，沿用 DS 口径不启用附加条件。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS[:3]:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 30.0}, source="hour"))
        history = [20.0, 20.0, 20.0, 30.0, 40.0] if sid == "a" else [70.0] * 5
        rows.extend(_history_rows(sid, history, slot))
        rows.append(_row(sid, slot, {"pm10": 55.0 if sid == "a" else 70.0}))
    outcome = _cycle(rows, slot)
    rises = _slot_values(outcome, "continuous_rise")
    assert len(rises) == 1 and rises[0]["station_id"] == "a"
    assert rises[0]["detail"]["peer_trimmed_mean"] is None


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


def test_ol_suppresses_passive_outlier_from_peer_drop():
    # 本站 CO 保持 0.6，其余站由 0.6 降至 0.3：相对偏差虽达 100%，但
    # 本站自身未升高，属于邻站下降造成的被动离群，不应累计 OL 窗口。
    slot = datetime(2026, 11, 22, 7, 15, tzinfo=TZ)
    states = MemStates()
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"co": 0.6}, source="hour"))
        rows.extend(_history_rows(sid, [0.6] * 4, slot, column="co"))
        rows.append(_row(sid, slot, {"co": 0.6 if sid == "a" else 0.3}))
    outcome = _cycle(rows, slot, states=states)

    assert _slot_values(outcome, "spatial_outlier") == []
    assert states.instance("5min", "a", "CO", "OL")["streak_cnt"] == 0


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


def test_pm25_hourly_ds_suppressed_below_peer_trimmed_mean():
    # 小时版同样受附加条件约束：a 50→65（轻度档阈值 12.5 过、邻站同向 0），
    # 对照站 [40,40,90,90,90] 去极值均值 ≈73.3 → 65 < 73.3 → 抑制。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    base = {"a": 50.0, "b": 90.0, "c": 90.0, "d": 90.0, "e": 40.0, "f": 40.0}
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, hour - timedelta(hours=1), {"pm25": base[sid]}, source="hour"))
        rows.append(_row(sid, hour, {"pm25": 65.0 if sid == "a" else base[sid]}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert [c for c in outcome.candidates if c["rule_type"] == "sudden_rise"] == []


def test_pm25_hourly_marked_current_value_is_invalid():
    # 小时值带质控标记同样无效：当前槽带标记不判 DS/OL，且不参与 1h 选档
    #（望田路111号 2026-11-13 12/13 点零值校准场景）。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, hour - timedelta(hours=1), {"pm25": 40.0}, source="hour"))
        marks = {"pm25": "H"} if sid == "a" else None
        rows.append(_row(sid, hour, {"pm25": 200.0 if sid == "a" else 40.0}, marks=marks, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert ("hour", "a", "PM2.5") not in outcome.current_values
    assert all(c["station_id"] != "a" for c in outcome.candidates)


def test_pm25_hourly_marked_baseline_hour_breaks_ds():
    # 基线小时带标记 → 基线缺失、DS 不判，不再产生“基线 0”的伪突升
    #（2026-11-13 14:00 实际案例：13:00 标记零值进基线，baseline=0 误报）。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        marks = {"pm25": "BB"} if sid == "a" else None
        rows.append(_row(sid, hour - timedelta(hours=1), {"pm25": 0.0}, marks=marks, source="hour"))
        rows.append(_row(sid, hour, {"pm25": 28.0 if sid == "a" else 40.0}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert [c for c in outcome.candidates if c["rule_type"] == "sudden_rise" and c["station_id"] == "a"] == []


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
    assert rises[0]["detail"]["peer_trimmed_mean"] == 40.0


def test_pm25_hourly_cl_suppressed_below_peer_trimmed_mean():
    # 小时版采用同一附加条件：本站累计抬升达标但仍低于其他站去极值均值。
    hour0 = datetime(2026, 9, 12, 6, 0, tzinfo=TZ)
    series = [40.0, 55.0, 65.0, 75.0]
    peers = {"b": 90.0, "c": 90.0, "d": 90.0, "e": 80.0, "f": 80.0}
    rows = []
    for sid in STATIONS:
        rows.extend(_hour_rows(
            [(hour0 + timedelta(hours=i), series[i] if sid == "a" else peers[sid]) for i in range(4)],
            sid,
        ))
    rises = []
    for index in range(len(series)):
        outcome = evaluate_pm25_hourly_cycle(
            rows, target_hour=hour0 + timedelta(hours=index),
            config=AirAlertRuleConfig(), states=MemStates(),
        )
        rises.extend(c for c in outcome.candidates if c["rule_type"] == "continuous_rise")
    assert rises == []


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
# 2026-11-20 起 ≥2 站共升由 MR 接管（覆盖涉事 CL），本节用 mr_enabled=False
# 测试 CL 合并作为 MR 关闭时的兜底路径。

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
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 70.0, "e": 40.0, "f": 40.0}, config=AirAlertRuleConfig(mr_enabled=False))
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
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 70.0, "e": 40.0, "f": 40.0}, config=AirAlertRuleConfig(mr_enabled=False))
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
    outcome = _regional_cl_run({"a": 70.0, "b": 70.0, "c": 70.0, "d": 40.0, "e": 40.0, "f": 40.0}, config=AirAlertRuleConfig(mr_enabled=False))
    rises = [c for c in outcome.candidates if c["rule_type"] == "continuous_rise"]
    assert len(rises) == 3
    assert outcome.region_merged == []


def test_regional_rise_merge_can_be_disabled():
    # cl_region_merge_sites=0：不合并。6 站完全同值时去极值均值等于末值，
    # 新的附加条件会全部拦截；构造 4 站高于对照均值、2 个低值站被拦截。
    outcome = _regional_cl_run(
        {"a": 100.0, "b": 100.0, "c": 100.0, "d": 100.0, "e": 40.0, "f": 50.0},
        config=AirAlertRuleConfig(cl_region_merge_sites=0, mr_enabled=False),
    )
    assert len([c for c in outcome.candidates if c["rule_type"] == "continuous_rise"]) == 4


# ---- DS 区域合并（2026-11-18 缝隙修复）----
# 恰好 2 站同窗口双命中 DS 时，彼此的邻站同向抑制（阈值 2）都不到门槛，
# 会推出两条互相矛盾的"单点突升"；ds_region_merge_sites=2 收口为一条。
# 2026-11-20 起 MR（多站同步抬升）默认接管双站共升场景，本节用
# mr_enabled=False 测试 DS 合并作为 MR 关闭时的兜底路径。

def _dual_ds_run(config: AirAlertRuleConfig | None = None):
    """两站同窗口双命中 DS：a 40→55（Δ15）、b 40→57（Δ17），其余 4 站走平。

    良档（小时 60 → PM10 良）阈值 max(40×0.3, 15)=15，两站都过；彼此的
    邻站同向计数 1 < 2 互不抑制；剔除极值均值 40，两站都高于均值。
    """
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        hour_value = 60.0 if sid in {"a", "b"} else 40.0
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": hour_value}, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
    current = {"a": 55.0, "b": 57.0, "c": 40.0, "d": 40.0, "e": 40.0, "f": 40.0}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": current[sid]}))
    return _cycle(rows, slot, config=config)


def test_dual_sudden_rise_merged_to_single_primary():
    # 两站双命中 DS → 合并为一条：跳变增量最大的站（b，Δ17）做主告警，
    # a 进 region_stations 清单与 region_merged 抑制流水。
    outcome = _dual_ds_run(config=AirAlertRuleConfig(mr_enabled=False))
    rises = [c for c in outcome.candidates if c["rule_type"] == "sudden_rise"]
    assert len(rises) == 1
    primary = rises[0]
    assert primary["station_id"] == "b"
    assert primary["region_merged_count"] == 2
    assert len(primary["detail"]["region_stations"]) == 1
    peer = primary["detail"]["region_stations"][0]
    assert peer["station_id"] == "a"
    assert peer["delta"] == 15.0 and peer["baseline"] == 40.0
    assert peer["station_value"] == 55.0
    assert len(outcome.region_merged) == 1
    assert outcome.region_merged[0]["station_id"] == "a"


def test_dual_sudden_rise_merge_can_be_disabled():
    # ds_region_merge_sites=0：不合并，两站各自保留候选（旧行为）。
    outcome = _dual_ds_run(config=AirAlertRuleConfig(ds_region_merge_sites=0, mr_enabled=False))
    rises = [c for c in outcome.candidates if c["rule_type"] == "sudden_rise"]
    assert len(rises) == 2
    assert {c["station_id"] for c in rises} == {"a", "b"}
    assert outcome.region_merged == []


def test_dual_sudden_rise_merge_audited_in_push_log(tmp_path):
    # 被合并站以 regional_merge 抑制入库：不推送、流水 merged_into_event_id
    # 指回主告警，与 CL 区域合并同一管线。
    outcome = _dual_ds_run(config=AirAlertRuleConfig(mr_enabled=False))
    primary = next(c for c in outcome.candidates if c["rule_type"] == "sudden_rise")
    loser = outcome.region_merged[0]
    loser["suppress_reason"] = "regional_merge"
    loser["merged_into_event_id"] = primary["event_id"]
    store = AlertStateStore(tmp_path)
    log_store = PushLogStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=datetime(2026, 9, 12, 8, 10, tzinfo=TZ), log_store=log_store,
        recovery_metrics=outcome.recovery_metrics,
        pre_suppressed=[{"alert": loser, "reason": "regional_merge"}],
    )
    assert len(pushed) == 1 and pushed[0]["station_id"] == "b"
    assert [item["reason"] for item in suppressed] == ["regional_merge"]
    log_file = next(iter((tmp_path / "push_log").glob("*.jsonl")))
    entries = [json.loads(line) for line in log_file.read_text(encoding="utf-8").strip().splitlines()]
    merge_entries = [e for e in entries if e["reason"] == "regional_merge"]
    assert len(merge_entries) == 1
    assert merge_entries[0]["station_id"] == "a"
    assert merge_entries[0]["merged_into_event_id"] == primary["event_id"]


# ---- MR 多站同步抬升（2026-11-20 新增）----
# 与 DS 并列的规则类型且优先级最高（0）：双站共升/片区一致偏好正向告警，
# 触发即覆盖涉事站点的单站 DS/CL/OL 候选。参数经 11-13~11-18 全槽位回测校准。

def test_mr_co_rise_covers_dual_sudden_rise():
    # 默认配置：双站同窗口共升 → MR 接管（不再是两条"单点突升"）。
    outcome = _dual_ds_run()
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    mr = outcome.candidates[0]
    assert mr["station_id"] == "b"  # 幅度最大站做主告警（17/15 > 15/15）
    assert mr["rule_priority"] == 0
    assert mr["rule_label"] == "多站同步抬升"
    assert mr["detail"]["path"] == "co_rise"
    assert mr["detail"]["mr_tier"] == "push"
    assert {s["station_id"] for s in mr["detail"]["involved_stations"]} == {"a", "b"}
    assert {s["station_id"] for s in mr["detail"]["region_stations"]} == {"a"}
    covered = {item["station_id"]: item for item in outcome.region_merged}
    assert set(covered) == {"a", "b"}  # 主站自己的 DS 候选同样被覆盖
    assert all(item["merged_into_event_id"] == mr["event_id"] for item in covered.values())


def test_mr_co_rise_does_not_cover_other_pollutants():
    # PM10 双站共升可触发 MR，但不得吞掉同站 NO2 的独立候选。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {
            "pm10": 40.0, "no2": 60.0 if sid == "b" else 20.0,
        }, source="hour"))
        rows.extend(_history_rows(sid, [40.0] * 4, slot))
        rows.extend(_history_rows(sid, [20.0] * 4, slot, column="no2"))
        rows.append(_row(sid, slot, {
            "pm10": 57.0 if sid == "a" else (55.0 if sid == "b" else 40.0),
            "no2": 45.0 if sid == "b" else 20.0,
        }))
    outcome = _cycle(rows, slot)

    assert {c["rule_type"] for c in outcome.candidates} == {
        "multi_station_rise", "sudden_rise",
    }
    no2_ds = next(c for c in outcome.candidates if c["target_pollutant"] == "NO2")
    assert no2_ds["station_id"] == "b"
    assert no2_ds["event_id"] not in {
        item["event_id"] for item in outcome.region_merged
    }
    assert all(item["target_pollutant"] == "PM10" for item in outcome.region_merged)


def test_mr_co_rise_pushed_single_regional_notice(tmp_path):
    # 推送链：MR 推一条，被覆盖的单站候选以 regional_merge 抑制并指回 MR。
    outcome = _dual_ds_run()
    mr = outcome.candidates[0]
    store = AlertStateStore(tmp_path)
    log_store = PushLogStore(tmp_path)
    pushed, suppressed, summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=datetime(2026, 9, 12, 8, 10, tzinfo=TZ), log_store=log_store,
        recovery_metrics=outcome.recovery_metrics,
        pre_suppressed=[{"alert": item, "reason": "regional_merge"} for item in outcome.region_merged],
    )
    assert len(pushed) == 1 and pushed[0]["rule_type"] == "multi_station_rise"
    assert [item["reason"] for item in suppressed] == ["regional_merge", "regional_merge"]
    log_file = next(iter((tmp_path / "push_log").glob("*.jsonl")))
    entries = [json.loads(line) for line in log_file.read_text(encoding="utf-8").strip().splitlines()]
    merge_entries = [e for e in entries if e["reason"] == "regional_merge"]
    assert {e["station_id"] for e in merge_entries} == {"a", "b"}
    assert all(e["merged_into_event_id"] == mr["event_id"] for e in merge_entries)
    assert summary is not None and "多站同步抬升" in summary


def test_mr_rebound_guard_blocks_low_baseline_micro_rebound():
    # 低洼基线微反弹：基线当日分位 27% <30%、抬升后低于六站中位、幅度不足
    # 全阈值（6 < 10）→ 反弹守卫拦截，不产生任何候选（18 时双反弹场景）。
    slot = datetime(2026, 9, 12, 8, 35, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        if sid in {"a", "b"}:
            history = [30.0] * 8 + [5.0] * 3  # 基线=mean(5,5,5)=5，分位 3/11≈27%
        else:
            history = [12.0] * 6 + [13.0] * 5
        rows.extend(_history_rows(sid, history, slot))
        value = 11.0 if sid in {"a", "b"} else (12.0 if sid in {"c", "d"} else 13.0)
        rows.append(_row(sid, slot, {"pm10": value}))
    outcome = _cycle(rows, slot)
    assert outcome.candidates == []
    assert outcome.region_merged == []


def test_mr_absolute_floor_blocks_co_micro_drift():
    # CO 微漂移：rise 0.18 过 0.5×阈值(0.15) 但低于绝对下限 → 不触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    config = AirAlertRuleConfig(mr_absolute_floor={
        "PM2.5": 3.0, "PM10": 3.0, "SO2": 3.0, "NO2": 3.0, "CO": 0.2,
    })
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"co": 0.5}, source="hour"))
        rows.extend(_history_rows(sid, [0.2] * 4, slot, column="co"))
    current = {"a": 0.38, "b": 0.38, "c": 0.2, "d": 0.2, "e": 0.2, "f": 0.2}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"co": current[sid]}))
    outcome = _cycle(rows, slot, config=config)
    assert outcome.candidates == []


def test_mr_plausibility_cap_blocks_multi_station_data_glitch():
    # SO2 三站同刻 ~1000μg 平台故障（超物理上限）→ 本槽不产生任何候选
    # （三站 DS 会被邻站同向抑制，MR 被上限拦截）。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"so2": 20.0}, source="hour"))
        rows.extend(_history_rows(sid, [8.0] * 4, slot, column="so2"))
    current = {"a": 1000.0, "b": 990.0, "c": 1010.0, "d": 8.0, "e": 8.0, "f": 8.0}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"so2": current[sid]}))
    outcome = _cycle(rows, slot)
    assert outcome.candidates == []


def test_mr_path_b_district_outlier_merges_single_outlier():
    # 16:45 形态（连跑两槽建立 OL streak）：第二槽 a=38 离群成立但 wz≈1.2、
    # 伴生 f=37 达 0.5×阈值 → MR 一致偏高接管，孤立"站点离群"不再单独推。
    # 其余站基线与现值持平（b/f 本来就高、cde 本来就低），路径 A（共升）
    # 只有 a 一站达标 → 落入路径 B。
    slot0 = datetime(2026, 9, 12, 8, 40, tzinfo=TZ)
    states = MemStates()
    baseline_by_station = {"a": 20.0, "b": 31.0, "c": 18.0, "d": 19.0, "e": 20.0, "f": 37.0}
    current = {"a": 38.0, "b": 31.0, "c": 18.0, "d": 19.0, "e": 20.0, "f": 37.0}
    outcome = None
    for index in range(2):
        slot = slot0 + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
            rows.extend(_history_rows(sid, [baseline_by_station[sid]] * (4 + index), slot))
            rows.append(_row(sid, slot, {"pm10": current[sid]}))
        outcome = _cycle(rows, slot, states=states)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    mr = outcome.candidates[0]
    assert mr["detail"]["path"] == "co_deviation"
    assert mr["station_id"] == "a"
    assert mr["detail"]["mr_tier"] == "push"
    assert {s["station_id"] for s in mr["detail"]["involved_stations"]} == {"a", "f"}
    assert mr["detail"]["wz"] is not None and mr["detail"]["wz"]["a"] == pytest.approx(1.2, abs=0.1)
    assert {item["station_id"] for item in outcome.region_merged} == {"a"}
    assert outcome.region_merged[0]["merged_into_event_id"] == mr["event_id"]


def test_mr_genuine_outlier_keeps_single_station_alerts():
    # 单站真离群（wz≈5.9 ≥3.5）→ 不触发 MR，DS/OL 照常各自成报。
    slot0 = datetime(2026, 9, 12, 8, 40, tzinfo=TZ)
    states = MemStates()
    outcome = None
    for index in range(2):
        slot = slot0 + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 110.0 if sid == "a" else 60.0}, source="hour"))
            rows.extend(_history_rows(sid, [55.0] * (4 + index), slot))
        current = {"a": 78.0, "b": 53.0, "c": 48.0, "d": 55.0, "e": 57.0, "f": 58.0}
        for sid in STATIONS:
            rows.append(_row(sid, slot, {"pm10": current[sid]}))
        outcome = _cycle(rows, slot, states=states)
    types = {c["rule_type"] for c in outcome.candidates}
    assert "multi_station_rise" not in types
    assert "sudden_rise" in types and "spatial_outlier" in types


def test_mr_digest_tier_suppressed_by_push_chain(tmp_path):
    # 涉事站全为优档且主站幅度不足全阈值 → mr_tier=digest，推送链以
    # mr_digest 抑制（夜间免打扰之外的日报摘要口径）。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [20.0] * 4, slot))
    current = {"a": 26.0, "b": 26.0, "c": 20.0, "d": 20.0, "e": 20.0, "f": 20.0}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": current[sid]}))
    outcome = _cycle(rows, slot)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    assert outcome.candidates[0]["detail"]["mr_tier"] == "digest"
    store = AlertStateStore(tmp_path)
    log_store = PushLogStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=datetime(2026, 9, 12, 8, 10, tzinfo=TZ), log_store=log_store,
        recovery_metrics=outcome.recovery_metrics,
    )
    assert pushed == []
    assert [item["reason"] for item in suppressed] == ["mr_digest"]


def test_mr_low_baseline_rebound_digest_even_with_full_amplitude(tmp_path):
    # 低基线反弹不报送（2026-11-20 定版）：主站基线当日分位 27% <30%，
    # 即使幅度达全阈值 1.5×（绝对门槛在低基线放大）也降级 digest。
    slot = datetime(2026, 9, 12, 8, 35, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        if sid in {"a", "b"}:
            history = [30.0] * 8 + [5.0] * 3  # 基线=mean(5,5,5)=5，分位 3/11≈27%
        else:
            history = [12.0] * 6 + [13.0] * 5
        rows.extend(_history_rows(sid, history, slot))
        value = 15.0 if sid == "a" else (14.0 if sid == "b" else (12.0 if sid in {"c", "d"} else 13.0))
        rows.append(_row(sid, slot, {"pm10": value}))
    outcome = _cycle(rows, slot)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    assert outcome.candidates[0]["detail"]["mr_tier"] == "digest"
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=datetime(2026, 9, 12, 8, 40, tzinfo=TZ), log_store=PushLogStore(tmp_path),
        recovery_metrics=outcome.recovery_metrics,
    )
    assert pushed == []
    assert [item["reason"] for item in suppressed] == ["mr_digest"]


# ---- MR 渐升型共升（2026-11-22 定版：路径 A 补 CL 累计口径）----

def _hourly_mr_run(series_by_station: dict[str, list[float]], hour0: datetime):
    """小时粒度共升场景：series 为各站 h0..h3 的 PM2.5 小时值（4 个点）。"""
    rows = []
    for sid, series in series_by_station.items():
        rows.extend(_hour_rows(
            [(hour0 + timedelta(hours=index), value) for index, value in enumerate(series)],
            sid,
        ))
    target = hour0 + timedelta(hours=len(next(iter(series_by_station.values()))) - 1)
    return evaluate_pm25_hourly_cycle(
        rows, target_hour=target, config=AirAlertRuleConfig(), states=MemStates(),
    )


def test_mr_admits_gradual_cl_risers_to_regional_event():
    # 2026-11-22 22:00 实例复现：4 站同步爬坡到中度污染。a/b 末跳（12/14）
    # 不足 DS 半阈值（中度档 0.5×30=15）但 CL 累计（36/40）达 0.5×CL 阈值 →
    # 按渐升口径入 MR；c/d 末跳（40/38）按跳变口径入站。四站 + 全部单站
    # 候选（a/b 的 CL、c/d 的 DS、c 的 OL）合并为一条区域事件。
    hour0 = datetime(2026, 9, 12, 5, 0, tzinfo=TZ)
    outcome = _hourly_mr_run({
        "a": [90.0, 99.0, 114.0, 126.0],
        "b": [84.0, 100.0, 110.0, 124.0],
        "c": [90.0, 95.0, 100.0, 140.0],
        "d": [88.0, 92.0, 98.0, 136.0],
        "e": [70.0] * 4,
        "f": [70.0] * 4,
    }, hour0)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    mr = outcome.candidates[0]
    assert mr["detail"]["path"] == "co_rise"
    assert mr["detail"]["mr_tier"] == "push"
    admissions = {s["station_id"]: s["admission"] for s in mr["detail"]["involved_stations"]}
    assert admissions == {"a": "cl", "b": "cl", "c": "ds", "d": "ds"}
    assert len(outcome.region_merged) == 5
    assert {item["station_id"] for item in outcome.region_merged} == {"a", "b", "c", "d"}
    assert all(item["merged_into_event_id"] == mr["event_id"] for item in outcome.region_merged)


def test_mr_pure_gradual_co_rise_without_any_sudden_jump():
    # 纯渐升共升：两站末跳均不足 DS 半阈值、无任何跳变站，渐升口径入站后
    # MR 照常成立，单站 CL/OL 候选并入区域事件。
    hour0 = datetime(2026, 9, 12, 5, 0, tzinfo=TZ)
    outcome = _hourly_mr_run({
        "a": [90.0, 99.0, 114.0, 126.0],
        "b": [84.0, 100.0, 110.0, 124.0],
        "c": [70.0] * 4,
        "d": [70.0] * 4,
        "e": [70.0] * 4,
        "f": [70.0] * 4,
    }, hour0)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    mr = outcome.candidates[0]
    assert mr["detail"]["path"] == "co_rise"
    involved = {s["station_id"]: s["admission"] for s in mr["detail"]["involved_stations"]}
    assert involved == {"a": "cl", "b": "cl"}
    assert mr["station_id"] == "b"  # CL 累计幅度 40/30 > 36/30，b 做主站
    assert {item["station_id"] for item in outcome.region_merged} == {"a", "b"}


# ---- MR 区域一致上升（2026-11-23：低幅度、多数站、PM2.5 单周期）----

def test_mr_regional_trend_detects_citywide_gradual_pm25_rise():
    # 六站单小时同步缓慢上升，末跳远低于 DS 半阈值；当前小时即可识别，
    # 当前浓度最高的望田路（a）为主站。
    hour0 = datetime(2026, 9, 12, 17, 0, tzinfo=TZ)
    outcome = _hourly_mr_run({
        "a": [30.0, 31.0, 32.0, 36.0],
        "b": [25.0, 26.0, 27.0, 30.0],
        "c": [20.0, 21.0, 22.0, 25.0],
        "d": [22.0, 23.0, 24.0, 27.0],
        "e": [18.0, 19.0, 20.0, 23.0],
        "f": [24.0, 25.0, 26.0, 29.0],
    }, hour0)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    mr = outcome.candidates[0]
    assert mr["detail"]["path"] == "regional_trend"
    assert mr["station_id"] == "a"
    assert mr["detail"]["trend_hold_slots"] == 1
    assert mr["detail"]["regional_median_rise"] == 3.0
    assert len(mr["detail"]["involved_stations"]) == 6


def test_mr_regional_trend_pm25_triggers_on_first_rising_hour():
    # PM2.5 第一个上升小时即触发，不再等第二个上升小时。
    hour0 = datetime(2026, 9, 12, 17, 0, tzinfo=TZ)
    rows = []
    for index, sid in enumerate(STATIONS):
        rows.extend(_hour_rows([
            (hour0, 20.0 + index), (hour0 + timedelta(hours=1), 22.0 + index),
        ], sid))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour0 + timedelta(hours=1),
        config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    assert outcome.candidates[0]["detail"]["path"] == "regional_trend"
    assert outcome.candidates[0]["detail"]["trend_hold_slots"] == 1


def test_mr_regional_trend_pm25_single_cycle_micro_rise_does_not_trigger():
    hour0 = datetime(2026, 9, 12, 17, 0, tzinfo=TZ)
    rows = []
    for index, sid in enumerate(STATIONS):
        rows.extend(_hour_rows([
            (hour0, 20.0 + index), (hour0 + timedelta(hours=1), 21.0 + index),
        ], sid))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour0 + timedelta(hours=1),
        config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert outcome.candidates == []


def test_mr_regional_trend_five_minute_pollutant_still_requires_two_slots():
    # PM10 首个上升槽不触发区域趋势；第二个上升槽才满足持续性要求。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        rows.extend(_history_rows(sid, [20.0, 21.0, 23.0, 25.0], slot))
        rows.append(_row(sid, slot, {"pm10": 27.0}))
    # 首个上升槽单独构造，确保序列中不含任何未来槽。
    first_rows = []
    for sid in STATIONS:
        first_rows.append(_row(sid, slot - timedelta(hours=1), {"pm10": 40.0}, source="hour"))
        first_rows.extend(_history_rows(sid, [20.0, 21.0], slot))
    first = _cycle(first_rows, slot - timedelta(minutes=5))
    assert first.candidates == []
    outcome = _cycle(rows, slot)
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    assert outcome.candidates[0]["detail"]["path"] == "regional_trend"
    assert outcome.candidates[0]["detail"]["trend_hold_slots"] == 2


def test_mr_regional_trend_rejects_minority_or_flat_micro_drift():
    hour0 = datetime(2026, 9, 12, 17, 0, tzinfo=TZ)
    minority = {sid: [20.0, 21.0, 22.0, 23.0] for sid in STATIONS[:2]}
    minority.update({sid: [20.0] * 4 for sid in STATIONS[2:]})
    assert _hourly_mr_run(minority, hour0).candidates == []
    micro = {sid: [20.0, 20.2, 20.4, 20.6] for sid in STATIONS}
    assert _hourly_mr_run(micro, hour0).candidates == []


def test_mr_regional_trend_ignores_stations_without_pollution_level():
    # 缺上一小时等级的站不能混入区域趋势（候选构造要求等级可判定）。
    hour0 = datetime(2026, 9, 12, 17, 0, tzinfo=TZ)
    rows = []
    for index, sid in enumerate(STATIONS):
        series = [20.0 + index, 21.0 + index, 22.0 + index, 25.0 + index]
        moments = [hour0 + timedelta(hours=i) for i in range(4)]
        rows.extend(_hour_rows(list(zip(moments[:2], series[:2])), sid))
        rows.extend(_hour_rows(list(zip(moments[2:], series[2:])), sid))
        if sid == "f":
            rows = [row for row in rows if not (
                row["station_id"] == "f" and row["data_time"] == moments[-1]
            )]
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour0 + timedelta(hours=3),
        config=AirAlertRuleConfig(), states=MemStates(),
    )
    assert [c["rule_type"] for c in outcome.candidates] == ["multi_station_rise"]
    assert len(outcome.candidates[0]["detail"]["involved_stations"]) == 5


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
