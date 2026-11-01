"""推送管控（M 链）测试——对应《算法需求文档》§9 与验收用例 T07/T08/T10/T11/T12。"""

from __future__ import annotations

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


def _alert(station_id: str = "a", rule_type: str = "limit_breach", level: int = 3,
           pollutant: str = "PM10", grain: str = "5min",
           occurred_at: str = "2026-11-02T09:00:00+08:00",
           recovery_threshold: float = 120.0) -> dict[str, Any]:
    return {
        "event_id": f"e-{station_id}-{rule_type}-{level}-{pollutant}",
        "occurred_at": occurred_at,
        "city": "许昌市",
        "station_id": station_id,
        "station_name": station_id,
        "target_pollutant": pollutant,
        "measurement_granularity": grain,
        "rule_type": rule_type,
        "rule_label": {"limit_breach": "限值突破", "sudden_rise": "突升",
                       "continuous_rise": "连续抬升", "spatial_outlier": "空间离群"}[rule_type],
        "alert_level": level,
        "alert_level_name": {1: "一级", 2: "二级", 3: "三级"}[level],
        "station_value": 200.0,
        "recovery_threshold": recovery_threshold,
        "detail": {},
    }


def _chain(candidates, store, tmp_path, now, **kwargs):
    kwargs.setdefault("log_store", PushLogStore(tmp_path))
    kwargs.setdefault("current_values", {})
    return apply_push_chain(candidates, store=store, config=AirAlertRuleConfig(), now=now, **kwargs)


def test_first_alert_pushes_and_disarms(tmp_path):
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    state = store.instance("5min", "a", "PM10", "limit_breach")
    assert state["armed"] is False
    assert state["last_level"] == 3
    assert store.global_push_count("2026-11-02") == 1


def test_same_level_within_cooldown_is_suppressed(tmp_path):
    # T07：三级推送后 60 分钟再次三级 → 不推送。armed 防抖先拦截（闸门
    # 顺序与文档 §9.1 伪代码一致），冷却期在恢复武装后兜底。
    store = AlertStateStore(tmp_path)
    now = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    _chain([_alert()], store, tmp_path, now)
    second = _alert(occurred_at="2026-11-02T10:00:00+08:00")
    second["event_id"] = "e-second"
    pushed, suppressed, _summary = _chain([second], store, tmp_path, datetime(2026, 11, 2, 10, 0, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] == "hysteresis"


def test_cooldown_applies_after_rearm_and_expires(tmp_path):
    # 三级推送（09:00，阈值 120）→ 三个周期回落确认重新武装（09:05/10/15，
    # 当前值 100 ≤ 108）→ 恢复后 09:15 仍在 120 分钟冷却内 → 冷却兜底拦截；
    # 11:05 冷却过期 → 同级告警放行。
    store = AlertStateStore(tmp_path)
    config = AirAlertRuleConfig()
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    key = ("5min", "a", "PM10")
    recovered = _alert(occurred_at="2026-11-02T09:05:00+08:00")
    recovered["event_id"] = "e-recover"
    _chain([recovered], store, tmp_path, datetime(2026, 11, 2, 9, 5, tzinfo=TZ), current_values={key: 100.0})
    rearm = _alert(occurred_at="2026-11-02T09:10:00+08:00")
    rearm["event_id"] = "e-rearm"
    _chain([rearm], store, tmp_path, datetime(2026, 11, 2, 9, 10, tzinfo=TZ), current_values={key: 100.0})
    rebound = _alert(occurred_at="2026-11-02T09:15:00+08:00")
    rebound["event_id"] = "e-rebound"
    pushed, suppressed, _summary = _chain(
        [rebound], store, tmp_path, datetime(2026, 11, 2, 9, 15, tzinfo=TZ), current_values={key: 100.0}
    )
    # 第 3 个回落周期（09:15 链）触发重新武装，但仍在三级冷却（120 分钟）内。
    state = store.instance("5min", "a", "PM10", "limit_breach")
    assert state["armed"] is True
    assert pushed == [] and suppressed[0]["reason"] == "cooldown"
    later = _alert(occurred_at="2026-11-02T11:05:00+08:00")
    later["event_id"] = "e-later"
    pushed2, _s2, _w2 = _chain([later], store, tmp_path, datetime(2026, 11, 2, 11, 5, tzinfo=TZ), current_values={key: 100.0})
    assert len(pushed2) == 1   # 冷却期已过


def test_escalation_penetrates_cooldown(tmp_path):
    # T08：冷却期内三级升级为二级（级别数字变小）→ 立即推送并刷新冷却。
    store = AlertStateStore(tmp_path)
    now = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    _chain([_alert(level=3, recovery_threshold=180.0)], store, tmp_path, now)
    escalated = _alert(level=2, occurred_at="2026-11-02T09:30:00+08:00")
    escalated["event_id"] = "e-escalated"
    pushed, suppressed, _summary = _chain([escalated], store, tmp_path, datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    state = store.instance("5min", "a", "PM10", "limit_breach")
    assert state["last_level"] == 2
    assert state["last_push_ts"].startswith("2026-11-02T09:30")


def test_hysteresis_blocks_until_recovered(tmp_path):
    # §9.2：推送后连续 3 个周期 ≤阈值×90% 才重新武装；期间同级不重复推送；
    # 恢复武装后冷却期（二级 90 分钟）继续兜底。
    store = AlertStateStore(tmp_path)
    now = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    _chain([_alert(level=2, recovery_threshold=150.0)], store, tmp_path, now)
    key = ("5min", "a", "PM10")
    config = AirAlertRuleConfig()
    gate_time = datetime(2026, 11, 2, 9, 5, tzinfo=TZ)
    for index in range(1, 4):
        # 当前值 100 ≤ 150×0.9=135，逐周期计数。
        rearmed = recovery_pass(store, {key: 100.0}, config)
        state = store.instance("5min", "a", "PM10", "limit_breach")
        if index < 3:
            assert rearmed == []
            assert evaluate_gate(state, 2, gate_time, config) == "hysteresis"
    assert rearmed == [instance_key("5min", "a", "PM10", "limit_breach")]
    state = store.instance("5min", "a", "PM10", "limit_breach")
    assert state["armed"] is True and state["last_level"] == 2   # 恢复保留 last_level
    assert evaluate_gate(state, 2, gate_time, config) == "cooldown"     # 冷却兜底
    assert evaluate_gate(state, 2, datetime(2026, 11, 2, 10, 31, tzinfo=TZ), config) is None  # 91 分钟后过期


def test_recovery_counter_resets_on_rebound(tmp_path):
    store = AlertStateStore(tmp_path)
    commit_push(
        store, store.instance("5min", "a", "PM10", "limit_breach"),
        level=2, now=datetime(2026, 11, 2, 9, 0, tzinfo=TZ),
        recovery_threshold=150.0, station_id="a",
    )
    key = ("5min", "a", "PM10")
    assert recovery_pass(store, {key: 100.0}, AirAlertRuleConfig()) == []
    # 回弹超过阈值×90% → 计数清零，之后重新计数。
    assert recovery_pass(store, {key: 200.0}, AirAlertRuleConfig()) == []
    state = store.instance("5min", "a", "PM10", "limit_breach")
    assert state["recover_cnt"] == 0


def test_site_daily_quota_silences_sixth_level3(tmp_path):
    # T10：某站三级当日第 6 次 → 静默入库。
    store = AlertStateStore(tmp_path)
    day = "2026-11-02"
    for _ in range(5):
        store.increment_push(day, "a", 3)
    assert quota_reason(store, "a", 3, day, AirAlertRuleConfig()) == "quota"
    assert quota_reason(store, "a", 1, day, AirAlertRuleConfig()) is None   # 一级不限


def test_global_daily_cap_silences_level2_after_40(tmp_path):
    # T11：全局日推送达 40 后，二级静默、一级不限。
    store = AlertStateStore(tmp_path)
    day = "2026-11-02"
    for index in range(40):
        store.increment_push(day, f"s{index % 6}", 2)
    assert quota_reason(store, "a", 2, day, AirAlertRuleConfig()) == "global_cap"
    assert quota_reason(store, "a", 1, day, AirAlertRuleConfig()) is None


def test_quiet_hours_silence_level3_only(tmp_path):
    # T12：22:30 三级静默入库；二级不受免打扰限制。
    config = AirAlertRuleConfig()
    assert config.in_quiet_hours(22) and config.in_quiet_hours(2)
    assert not config.in_quiet_hours(6) and not config.in_quiet_hours(21)
    store = AlertStateStore(tmp_path)
    night = datetime(2026, 11, 2, 22, 30, tzinfo=TZ)
    pushed, suppressed, _summary = _chain([_alert(level=3)], store, tmp_path, night)
    assert pushed == [] and suppressed[0]["reason"] == "quiet_hours"
    level2 = _alert(level=2)
    level2["event_id"] = "e-l2-night"
    pushed2, _s2, _w2 = _chain([level2], store, tmp_path, night)
    assert len(pushed2) == 1


def test_same_station_multi_rule_merges_into_one_primary(tmp_path):
    # §9.3.1：同站多条规则保留最高级别（一级/二级高于三级）。
    store = AlertStateStore(tmp_path)
    candidates = [
        _alert(rule_type="limit_breach", level=3),
        _alert(rule_type="spatial_outlier", level=2, pollutant="PM10"),
    ]
    candidates[1]["event_id"] = "e-a-r4"
    pushed, suppressed, _summary = _chain(candidates, store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    assert len(pushed) == 1
    primary = pushed[0]
    assert primary["rule_type"] == "spatial_outlier" and primary["alert_level"] == 2
    assert primary["concurrent_rules"][0]["rule_type"] == "limit_breach"
    assert suppressed == []


def test_push_log_records_push_and_suppress(tmp_path):
    import json as _json

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
    # §11：重启后从状态文件恢复 armed/冷却期。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    reopened = AlertStateStore(tmp_path)
    state = reopened.instance("5min", "a", "PM10", "limit_breach")
    assert state["armed"] is False and state["last_level"] == 3
    assert evaluate_gate(state, 3, datetime(2026, 11, 2, 9, 30, tzinfo=TZ), AirAlertRuleConfig()) == "hysteresis"
