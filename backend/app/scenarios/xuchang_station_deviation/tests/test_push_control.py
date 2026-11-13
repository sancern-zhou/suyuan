"""推送管控（M 链）测试（判据修订版）。

覆盖：按规则/因子冷却、#23 升级例外（污染等级升高穿透冷却）、
#24 优先级（DS > CL > OL）、恢复防抖、限额、免打扰、同站合并、流水。
"""

from __future__ import annotations

import json as _json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_station_deviation.push_control import (
    AlertStateStore,
    PushLogStore,
    apply_push_chain,
    commit_push,
    evaluate_gate,
    instance_key,
    quota_reason,
    recovery_pass,
)
from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig

TZ = ZoneInfo("Asia/Shanghai")


def _alert(station_id: str = "a", rule_type: str = "sudden_rise",
           pollutant: str = "PM10", grain: str = "5min",
           occurred_at: str = "2026-11-02T09:00:00+08:00",
           air_quality_level: str = "良",
           recovery_threshold: float = 15.0) -> dict[str, Any]:
    return {
        "event_id": f"e-{station_id}-{rule_type}-{pollutant}",
        "occurred_at": occurred_at,
        "city": "许昌市",
        "station_id": station_id,
        "station_name": station_id,
        "target_pollutant": pollutant,
        "measurement_granularity": grain,
        "rule_type": rule_type,
        "rule_label": {"sudden_rise": "单点突升", "continuous_rise": "连续抬升",
                       "spatial_outlier": "站点离群"}[rule_type],
        "rule_priority": {"sudden_rise": 1, "continuous_rise": 2, "spatial_outlier": 3}[rule_type],
        "air_quality_level": air_quality_level,
        "station_value": 55.0,
        "recovery_threshold": recovery_threshold,
        "detail": {},
    }


def _chain(candidates, store, tmp_path, now, **kwargs):
    kwargs.setdefault("log_store", PushLogStore(tmp_path))
    kwargs.setdefault("recovery_metrics", {})
    return apply_push_chain(candidates, store=store, config=AirAlertRuleConfig(), now=now, **kwargs)


def test_first_alert_pushes_and_disarms(tmp_path):
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    state = store.instance("5min", "a", "PM10", "sudden_rise")
    assert state["armed"] is False
    assert state["last_air_level"] == "良"
    assert store.global_push_count("2026-11-02") == 1


def test_same_rule_within_cooldown_is_suppressed(tmp_path):
    # DS（PM10）冷却 30 分钟：09:00 推送后，09:15 再次命中 → 冷却拦截。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    second = _alert(occurred_at="2026-11-02T09:15:00+08:00")
    second["event_id"] = "e-second"
    pushed, suppressed, _summary = _chain([second], store, tmp_path, datetime(2026, 11, 2, 9, 15, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] in {"cooldown", "hysteresis"}


def test_cooldown_differs_by_rule_and_pollutant(tmp_path):
    # DS-PM2.5 冷却 60 分钟；DS-PM10 冷却 30 分钟；CL-PM10 冷却 60 分钟。
    config = AirAlertRuleConfig()
    assert config.cooldown_for("sudden_rise", "PM2.5") == 60
    assert config.cooldown_for("sudden_rise", "PM10") == 30
    assert config.cooldown_for("continuous_rise", "PM10") == 60
    assert config.cooldown_for("continuous_rise", "PM2.5") == 120
    assert config.cooldown_for("spatial_outlier", "NO2") == 30


def test_level_upgrade_penetrates_cooldown(tmp_path):
    # #23：冷却期内污染等级由良升至轻度 → 立即推送，带升级标识。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    escalated = _alert(occurred_at="2026-11-02T09:15:00+08:00", air_quality_level="轻度污染")
    escalated["event_id"] = "e-escalated"
    pushed, suppressed, _summary = _chain([escalated], store, tmp_path, datetime(2026, 11, 2, 9, 15, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    assert pushed[0]["is_upgrade"] is True
    assert pushed[0]["upgrade_from_level"] == "良"
    assert pushed[0]["upgrade_to_level"] == "轻度污染"
    assert pushed[0]["upgrade_of_event_id"] == "e-a-sudden_rise-PM10"
    state = store.instance("5min", "a", "PM10", "sudden_rise")
    assert state["last_air_level"] == "轻度污染"
    assert state["last_push_ts"].startswith("2026-11-02T09:15")


def test_level_downgrade_still_suppressed(tmp_path):
    # 等级回落不穿透冷却：轻度推送后良档再次命中 → 正常拦截。
    store = AlertStateStore(tmp_path)
    _chain([_alert(air_quality_level="轻度污染")], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    later = _alert(occurred_at="2026-11-02T09:15:00+08:00", air_quality_level="良")
    later["event_id"] = "e-later"
    pushed, suppressed, _summary = _chain([later], store, tmp_path, datetime(2026, 11, 2, 9, 15, tzinfo=TZ))
    assert pushed == [] and suppressed


def test_priority_keeps_ds_over_cl_over_ol(tmp_path):
    # #24：同站同因子同窗口三条规则命中 → 只推 DS，CL/OL 以 priority 抑制。
    store = AlertStateStore(tmp_path)
    candidates = [
        _alert(rule_type="spatial_outlier"),
        _alert(rule_type="continuous_rise"),
        _alert(rule_type="sudden_rise"),
    ]
    for index, candidate in enumerate(candidates):
        candidate["event_id"] = f"e-{index}"
    pushed, suppressed, _summary = _chain(candidates, store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    assert len(pushed) == 1 and pushed[0]["rule_type"] == "sudden_rise"
    assert {item["alert"]["rule_type"] for item in suppressed} == {"continuous_rise", "spatial_outlier"}
    assert all(item["reason"] == "priority" for item in suppressed)


def test_same_rule_different_pollutant_not_priority_suppressed(tmp_path):
    # #24 范围是同站同因子：同站不同因子互不挤占（合并只影响通报组织）。
    store = AlertStateStore(tmp_path)
    candidates = [_alert(pollutant="PM10"), _alert(pollutant="NO2")]
    candidates[1]["event_id"] = "e-no2"
    pushed, suppressed, _summary = _chain(candidates, store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    assert suppressed == []
    assert {a["target_pollutant"] for a in pushed} == {"PM10", "NO2"}
    # 同站合并：NO2 优先级同为 DS，按污染物序取 PM10 作主告警。
    primary = next(a for a in pushed if a.get("concurrent_rules"))
    assert primary["target_pollutant"] == "PM10"
    assert primary["concurrent_rules"][0]["target_pollutant"] == "NO2"


def test_hysteresis_blocks_until_recovered(tmp_path):
    # 推送后连续 3 个周期 ≤阈值×90% 才重新武装；恢复后冷却期兜底。
    store = AlertStateStore(tmp_path)
    config = AirAlertRuleConfig()
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    key = ("5min", "a", "PM10", "sudden_rise")
    gate_time = datetime(2026, 11, 2, 9, 5, tzinfo=TZ)
    for index in range(1, 4):
        # 恢复指标 10 ≤ 15×0.9=13.5，逐周期计数。
        rearmed = recovery_pass(store, {key: 10.0}, config)
        state = store.instance("5min", "a", "PM10", "sudden_rise")
        if index < 3:
            assert rearmed == []
            assert evaluate_gate(
                state, rule_type="sudden_rise", pollutant="PM10",
                air_quality_level="良", now=gate_time, config=config,
            ) == "hysteresis"
    assert rearmed == [instance_key("5min", "a", "PM10", "sudden_rise")]
    state = store.instance("5min", "a", "PM10", "sudden_rise")
    assert state["armed"] is True and state["last_air_level"] == "良"
    # 恢复后仍在 DS-PM10 冷却（30 分钟）内 → 冷却兜底；31 分钟后过期。
    assert evaluate_gate(
        state, rule_type="sudden_rise", pollutant="PM10",
        air_quality_level="良", now=gate_time, config=config,
    ) == "cooldown"
    assert evaluate_gate(
        state, rule_type="sudden_rise", pollutant="PM10",
        air_quality_level="良", now=datetime(2026, 11, 2, 9, 31, tzinfo=TZ), config=config,
    ) is None


def test_recovery_counter_resets_on_rebound(tmp_path):
    store = AlertStateStore(tmp_path)
    commit_push(
        store, store.instance("5min", "a", "PM10", "sudden_rise"),
        event_id="e-first", air_quality_level="良",
        now=datetime(2026, 11, 2, 9, 0, tzinfo=TZ),
        recovery_threshold=15.0, station_id="a",
    )
    key = ("5min", "a", "PM10", "sudden_rise")
    assert recovery_pass(store, {key: 10.0}, AirAlertRuleConfig()) == []
    # 回弹超过阈值×90% → 计数清零，之后重新计数。
    assert recovery_pass(store, {key: 55.0}, AirAlertRuleConfig()) == []
    state = store.instance("5min", "a", "PM10", "sudden_rise")
    assert state["recover_cnt"] == 0


def test_site_daily_quota_and_global_cap(tmp_path):
    # 站点日上限 8 条、全局日上限 40 条（不再区分告警级别）。
    store = AlertStateStore(tmp_path)
    day = "2026-11-02"
    for _ in range(8):
        store.increment_push(day, "a")
    assert quota_reason(store, "a", day, AirAlertRuleConfig()) == "quota"
    assert quota_reason(store, "b", day, AirAlertRuleConfig()) is None
    for index in range(40):
        store.increment_push(day, f"s{index % 6}")
    assert quota_reason(store, "b", day, AirAlertRuleConfig()) == "global_cap"


def test_quiet_hours_silence_outlier_only(tmp_path):
    # 22:30 站点离群（OL）静默入库；DS/CL 不受免打扰限制。
    config = AirAlertRuleConfig()
    assert config.in_quiet_hours(22) and config.in_quiet_hours(2)
    assert not config.in_quiet_hours(6) and not config.in_quiet_hours(21)
    store = AlertStateStore(tmp_path)
    night = datetime(2026, 11, 2, 22, 30, tzinfo=TZ)
    pushed, suppressed, _summary = _chain([_alert(rule_type="spatial_outlier")], store, tmp_path, night)
    assert pushed == [] and suppressed[0]["reason"] == "quiet_hours"
    pushed2, _s2, _w2 = _chain([_alert()], store, tmp_path, night)
    assert len(pushed2) == 1


def test_push_log_records_push_and_suppress(tmp_path):
    store = AlertStateStore(tmp_path)
    log_store = PushLogStore(tmp_path)
    morning = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    apply_push_chain([_alert()], store=store, config=AirAlertRuleConfig(), now=morning, log_store=log_store)
    later = _alert()
    later["event_id"] = "e-again"
    apply_push_chain([later], store=store, config=AirAlertRuleConfig(),
                     now=datetime(2026, 11, 2, 9, 5, tzinfo=TZ), log_store=log_store)
    log_files = list((tmp_path / "push_log").glob("*.jsonl"))
    assert len(log_files) == 1
    lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
    actions = [_json.loads(line)["action"] for line in lines]
    assert actions == ["push", "suppress"]
    assert _json.loads(lines[1])["reason"] == "hysteresis"


def test_state_survives_restart(tmp_path):
    # 重启后从状态文件恢复 armed/冷却期/等级。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    reopened = AlertStateStore(tmp_path)
    state = reopened.instance("5min", "a", "PM10", "sudden_rise")
    assert state["armed"] is False and state["last_air_level"] == "良"
    assert state["first_event_id"] == "e-a-sudden_rise-PM10"
