"""分级告警规则引擎测试——对应《算法需求文档》§13 验收用例（T01-T15 节选）。

时间线均使用 Asia/Shanghai 时区的 5 分钟槽/整点槽；行数据用中大表字段
形态（``_mark`` 列表示质控标记，缺测/负值视为无效）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_station_deviation.push_control import (
    AlertStateStore,
    PushLogStore,
    apply_push_chain,
)
from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig
from app.scenarios.xuchang_station_deviation.rule_engine import (
    evaluate_five_minute_cycle,
    evaluate_pm25_hourly_cycle,
    delta_ratio,
    new_rule_state,
    trim_mean_others,
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


def _cycle(rows: list[dict[str, Any]], slot: datetime, level_name: str | None = "良",
           config: AirAlertRuleConfig | None = None, states: MemStates | None = None):
    return evaluate_five_minute_cycle(
        rows, target_slot=slot, config=config or AirAlertRuleConfig(),
        states=states or MemStates(), level_name=level_name,
    )


def _slot_values(outcome, rule_type: str | None = None) -> list[dict[str, Any]]:
    return [c for c in outcome.candidates if rule_type is None or c["rule_type"] == rule_type]


# ---- 公共计算组件（§3）----

def test_delta_ratio_follows_pollution_level():
    config = AirAlertRuleConfig()
    assert delta_ratio(0.30, 0, config) == 0.40   # 优良 +10pp
    assert delta_ratio(0.30, 1, config) == 0.40
    assert delta_ratio(0.30, 2, config) == 0.30   # 轻中度不修正
    assert abs(delta_ratio(0.30, 4, config) - 0.20) < 1e-9   # 重严重 -10pp
    assert abs(delta_ratio(0.30, 5, config) - 0.20) < 1e-9


def test_trim_mean_others_requires_five_valid_peers():
    values = {"a": 100.0, "b": 40.0, "c": 50.0, "d": 60.0, "e": 70.0, "f": 200.0}
    # 去掉最大 200 与最小 40，均值 60。
    assert trim_mean_others(values, "a") == 60.0
    four = {"a": 100.0, "b": 40.0, "c": 50.0, "d": 60.0, "e": 70.0}
    assert trim_mean_others(four, "a") is None     # 其余站不足 5 个，跳过 R4


def test_r1_limit_version_switches_in_2031():
    config = AirAlertRuleConfig()
    assert config.active_limit_version(date(2030, 12, 31))["tiers"]["PM10"]["良"] == 120
    assert config.active_limit_version(date(2031, 1, 1))["tiers"]["PM10"]["良"] == 100
    assert config.active_limit_version(date(2031, 1, 1))["tiers"]["PM2.5"]["良"] == 50


# ---- R1 限值突破（§4）----

def test_r1_good_period_pm10_125_is_level3():
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = [_row(sid, slot, {"pm10": 125 if sid == "a" else 100}) for sid in STATIONS]
    outcome = _cycle(rows, slot, level_name="良")
    breaches = _slot_values(outcome, "limit_breach")
    assert len(breaches) == 1
    alert = breaches[0]
    assert (alert["station_id"], alert["alert_level"]) == ("a", 3)
    assert alert["detail"]["limit_threshold"] == 120
    # 良档：125 < 120×1.2，只有三级。


def test_r1_secondary_and_primary_grades():
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = [_row(sid, slot, {"pm10": 150 if sid == "a" else 100}) for sid in STATIONS]
    outcome = _cycle(rows, slot, level_name="良")
    breaches = _slot_values(outcome, "limit_breach")
    assert len(breaches) == 1
    assert breaches[0]["alert_level"] == 2   # 150 ≥ 144

    slot2 = datetime(2026, 9, 12, 9, 5, tzinfo=TZ)
    rows2 = [_row(sid, slot2, {"o3": 210 if sid == "a" else 180}) for sid in STATIONS]
    outcome2 = _cycle(rows2, slot2, level_name="中度污染")
    primary = _slot_values(outcome2, "limit_breach")[0]
    assert primary["alert_level"] == 1                                    # 达到 1h 国标限值 200
    assert primary["detail"]["limit_1h"] == 200


# ---- R2 突升（§5）----

def _r2_scenario(slot: datetime, current: float, level_name: str = "中度污染",
                 base_value: float = 90.0, others: float = 90.0,
                 states: MemStates | None = None):
    rows = []
    for sid in STATIONS:
        history_values = [base_value] * 12
        rows.extend(_history_rows(sid, history_values, slot))
    for sid in STATIONS:
        value = current if sid == "a" else others
        rows.append(_row(sid, slot, {"pm10": value}))
    states = states or MemStates()
    outcome = _cycle(rows, slot, level_name=level_name, states=states)
    return outcome, states


def test_r2_level3_requires_two_period_confirmation():
    # T03：基线 90、中度时段，第一期 125（≥90×1.3）只记 streak，不触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome, states = _r2_scenario(slot, current=125)
    assert _slot_values(outcome, "sudden_rise") == []
    assert states.instance("5min", "a", "PM10", "R2")["streak_cnt"] == 1
    # 第二期仍满足 → 触发三级。
    slot2 = slot + timedelta(minutes=5)
    outcome2, states2 = _r2_scenario(slot2, current=130, states=states)
    rises = _slot_values(outcome2, "sudden_rise")
    assert len(rises) == 1 and rises[0]["alert_level"] == 3
    assert rises[0]["detail"]["confirm_streak"] == 2


def test_r2_immediate_for_secondary_grade():
    # 中度时段：130 ≥ 90×1.5=135 不成立；改用 140 ≥ 135 → 二级即时（无确认）。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome, _states = _r2_scenario(slot, current=140)
    rises = _slot_values(outcome, "sudden_rise")
    assert len(rises) == 1 and rises[0]["alert_level"] == 2


def test_r2_ratio_widens_in_good_period():
    # 优良时段修正 +10pp：三级阈值 90×1.4=126，125 不再满足原始三级条件。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome, _states = _r2_scenario(slot, current=125, level_name="良")
    assert _slot_values(outcome, "sudden_rise") == []
    assert outcome.region_event_stations == []


def test_r2_floor_blocks_low_absolute_values():
    # 绝对底线 F(PM10)=100：基线 50 时抬升比例满足，但 90 < 100 不触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    outcome, _states = _r2_scenario(slot, current=90, base_value=50.0, others=50.0, level_name="中度污染")
    assert _slot_values(outcome, "sudden_rise") == []


def test_r2_streak_resets_after_interruption():
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    _outcome, states = _r2_scenario(slot, current=125)
    assert states.instance("5min", "a", "PM10", "R2")["streak_cnt"] == 1
    # 下一周期回落 → 间断清零（§5.2）。
    slot2 = slot + timedelta(minutes=5)
    _outcome2, states2 = _r2_scenario(slot2, current=100, states=states)
    assert states2.instance("5min", "a", "PM10", "R2")["streak_cnt"] == 0


# ---- R3 连续抬升（§6）----

def test_r3_secondary_after_six_continuous_rises():
    # T04：自 90 连续 6 周期涨至 122（累计 35.6%）→ 二级；前 5 个周期累计
    # 始终不足 15%，不提前触发三级。每期涨幅均 ≥2%。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    series = [90.0, 92.0, 94.0, 96.0, 98.0, 102.0, 122.0]
    states = MemStates()
    candidates: list[dict[str, Any]] = []
    for index, value in enumerate(series):
        current_slot = slot + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            history = series[:index] if sid == "a" else [40.0] * max(index, 1)
            rows.extend(_history_rows(sid, history, current_slot))
            rows.append(_row(sid, current_slot, {"pm10": value if sid == "a" else 40.0}))
        outcome = _cycle(rows, current_slot, level_name="中度污染", states=states)
        candidates.extend(_slot_values(outcome, "continuous_rise"))
    assert len(candidates) == 1
    alert = candidates[0]
    assert alert["alert_level"] == 2
    assert alert["detail"]["streak_cnt"] == 6
    assert alert["rise_count"] == 6
    assert alert["total_rise_rate"] > 0.30


def test_r3_resets_after_missing_slot():
    # T15：缺测一个周期后连续计数清零，重新累计。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    series = [90.0, 93.0, 96.0, None, 96.0, 99.0, 102.0]
    states = MemStates()
    candidates: list[dict[str, Any]] = []
    for index, value in enumerate(series):
        current_slot = slot + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            history = [v for v in series[:index] if v is not None] if sid == "a" else [40.0] * index
            rows.extend(_history_rows(sid, history, current_slot))
            if value is not None:
                rows.append(_row(sid, current_slot, {"pm10": value if sid == "a" else 40.0}))
        outcome = _cycle(rows, current_slot, level_name="中度污染", states=states)
        candidates.extend(_slot_values(outcome, "continuous_rise"))
    # 缺测打断后（且首轮第 4 期持平归零）最多只重新累计到 2 个周期（<4），
    # 不应有任何 R3 告警。
    assert candidates == []


# ---- R4 空间离群（§7）----

def _r4_scenario(slot: datetime, target_value: float, peer_value: float = 55.0,
                 level_name: str = "中度污染", pollutant: str = "no2",
                 states: MemStates | None = None, periods: int = 1):
    states = states or MemStates()
    candidates = []
    for index in range(periods):
        current_slot = slot + timedelta(minutes=5 * index)
        rows = []
        for sid in STATIONS:
            value = target_value if sid == "a" else peer_value
            rows.append(_row(sid, current_slot, {pollutant: value}))
        outcome = _cycle(rows, current_slot, level_name=level_name, states=states)
        candidates.extend(_slot_values(outcome, "spatial_outlier"))
    return candidates, states


def test_r4_level3_requires_three_persistent_periods():
    # T05：S 站 NO2=96、其余均值 55：仅持续 2 周期不触发，第 3 周期触发三级。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    candidates, _states = _r4_scenario(slot, 96.0, periods=2)
    assert candidates == []
    candidates, _states = _r4_scenario(slot, 96.0, periods=3)
    assert len(candidates) == 1 and candidates[0]["alert_level"] == 3
    assert candidates[0]["detail"]["hold_streak"] == 3


def test_r4_primary_grade_is_immediate():
    # 一级（≥3 倍）即时：120 ≥ 55×3=165 不成立；用 170 触发。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    candidates, _states = _r4_scenario(slot, 170.0)
    assert len(candidates) == 1 and candidates[0]["alert_level"] == 1


def test_r4_heavy_pollution_relaxes_multiples():
    # 重度污染倍率各减 0.5：二级阈值 55×1.5=82.5 → 96 满足二级（持续 2 周期）。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    candidates, _states = _r4_scenario(slot, 96.0, level_name="重度污染", periods=2)
    assert len(candidates) == 1 and candidates[0]["alert_level"] == 2
    assert candidates[0]["detail"]["multiples_effective"][2] == 1.5


def test_region_event_stations_from_raw_r2_hits():
    # T06（引擎侧）：4 个站点满足 R2 三级原始条件 → 计入区域过程站点。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.extend(_history_rows(sid, [90.0] * 12, slot))
    current = {"a": 130.0, "b": 130.0, "c": 130.0, "d": 130.0, "e": 90.0, "f": 90.0}
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": current[sid]}))
    outcome = _cycle(rows, slot, level_name="中度污染")
    assert set(outcome.region_event_stations) == {"a", "b", "c", "d"}


def test_baseline_below_minimum_skips_relative_rules():
    # §11：有效值 <8 → 跳过 R2/R3；R1、R4 照常。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.extend(_history_rows(sid, [90.0] * 7, slot))
    for sid in STATIONS:
        rows.append(_row(sid, slot, {"pm10": 200 if sid == "a" else 90.0}))
    states = MemStates()
    outcome = _cycle(rows, slot, level_name="中度污染", states=states)
    assert _slot_values(outcome, "sudden_rise") == []
    assert _slot_values(outcome, "continuous_rise") == []
    assert outcome.region_event_stations == []
    # R1 照常：200 ≥ 200×?；中度档 T=200 → 三级。
    assert any(c["rule_type"] == "limit_breach" and c["alert_level"] == 3 for c in outcome.candidates)


def test_marked_current_value_is_invalid():
    # 质控标记（§2.1 有效性约定）：带标记的当前值不参与判定。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        rows.extend(_history_rows(sid, [90.0] * 12, slot))
    for sid in STATIONS:
        marks = {"pm10": "质控"} if sid == "a" else None
        rows.append(_row(sid, slot, {"pm10": 200 if sid == "a" else 90.0}, marks=marks))
    outcome = _cycle(rows, slot, level_name="中度污染")
    assert ("5min", "a", "PM10") not in outcome.current_values
    assert all(c["station_id"] != "a" for c in outcome.candidates)


# ---- PM2.5 小时版（§8）----

def test_pm25_hourly_r1_and_r2():
    # T13：小时值 65（良档 ≥60）→ R1 三级；同时 R2 小时版三级
    # （65 ≥ 50×1.25=62.5 且差 15 ≥ 15）。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    rows = []
    for sid in STATIONS:
        for hours_back in (3, 2, 1):
            rows.append(_row(sid, hour - timedelta(hours=hours_back), {"pm25": 50 if sid == "a" else 40.0}, source="hour"))
        rows.append(_row(sid, hour, {"pm25": 65 if sid == "a" else 40.0}, source="hour"))
    outcome = evaluate_pm25_hourly_cycle(
        rows, target_hour=hour, config=AirAlertRuleConfig(), states=MemStates(),
    )
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for candidate in outcome.candidates:
        by_rule.setdefault(candidate["rule_type"], []).append(candidate)
    assert {c["alert_level"] for c in by_rule["limit_breach"]} == {3}
    assert {c["alert_level"] for c in by_rule["sudden_rise"]} == {3}
    assert by_rule["sudden_rise"][0]["detail"]["absolute_gain"] == 15.0


def test_pm25_hourly_r3_two_hour_rise():
    # 连续 2 小时上涨（+10%、+18.2%），累计 30% ≥ 15% → 三级。
    hour = datetime(2026, 9, 12, 8, 0, tzinfo=TZ)
    series = [40.0, 44.0, 52.0]
    rows = []
    for sid in STATIONS:
        for index, value in enumerate(series):
            rows.append(_row(sid, hour - timedelta(hours=2 - index), {"pm25": value if sid == "a" else 40.0}, source="hour"))
    states = MemStates()
    rises: list[dict[str, Any]] = []
    for index in range(len(series)):
        target = hour - timedelta(hours=2 - index)
        outcome = evaluate_pm25_hourly_cycle(
            rows, target_hour=target, config=AirAlertRuleConfig(), states=states,
        )
        rises.extend(c for c in outcome.candidates if c["rule_type"] == "continuous_rise")
    assert len(rises) == 1 and rises[0]["alert_level"] == 3
    assert rises[0]["measurement_granularity"] == "hour"
    assert rises[0]["detail"]["streak_cnt"] == 2


# ---- 推送链协同（引擎产物 → 管控）----

def test_region_event_suppresses_spatial_outliers_in_chain(tmp_path):
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    rows = [_row(sid, slot, {"no2": 170 if sid == "a" else 55.0}) for sid in STATIONS]
    outcome = _cycle(rows, slot, level_name="中度污染")
    spatial = _slot_values(outcome, "spatial_outlier")
    assert spatial and spatial[0]["alert_level"] == 1   # 170 ≥ 55×3 → 一级即时
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = apply_push_chain(
        list(outcome.candidates), store=store, config=AirAlertRuleConfig(),
        now=slot, log_store=PushLogStore(tmp_path),
        current_values=outcome.current_values, region_event=True,
    )
    assert pushed == []
    assert all(item["reason"] == "region_event" for item in suppressed)
    store.save()


def test_window_summary_covers_three_stations(tmp_path):
    # T09：同窗口 3 个站点各一条三级 → 合并为一条摘要。
    slot = datetime(2026, 9, 12, 8, 5, tzinfo=TZ)
    candidates = []
    for sid in ("a", "c", "e"):
        candidates.append({
            "event_id": f"e-{sid}", "occurred_at": slot.isoformat(), "city": "许昌市",
            "station_id": sid, "station_name": sid, "target_pollutant": "PM10",
            "measurement_granularity": "5min", "rule_type": "limit_breach",
            "rule_label": "限值突破", "alert_level": 3, "alert_level_name": "三级",
            "station_value": 125.0, "recovery_threshold": 120.0, "detail": {},
        })
    store = AlertStateStore(tmp_path)
    pushed, suppressed, summary = apply_push_chain(
        candidates, store=store, config=AirAlertRuleConfig(), now=slot,
        log_store=PushLogStore(tmp_path),
    )
    assert len(pushed) == 3 and suppressed == []
    assert summary is not None and summary.count("- ") == 3
