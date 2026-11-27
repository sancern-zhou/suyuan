"""推送管控（M 链）测试（判据修订版）。

覆盖：按规则/因子冷却、#23 升级例外（污染等级升高穿透冷却）、
#24 优先级（DS > CL > OL）、恢复防抖、限额、免打扰、同站合并、流水、
MR 单向覆盖单站共享冷却（2026-11-25 定版）。
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
                       "spatial_outlier": "站点离群", "multi_station_rise": "多站同步抬升"}[rule_type],
        "rule_priority": {"sudden_rise": 1, "continuous_rise": 2, "spatial_outlier": 3,
                          "multi_station_rise": 0}[rule_type],
        "air_quality_level": air_quality_level,
        "station_value": 55.0,
        "recovery_threshold": recovery_threshold,
        "detail": {},
    }


def _chain(candidates, store, tmp_path, now, **kwargs):
    kwargs.setdefault("log_store", PushLogStore(tmp_path))
    kwargs.setdefault("recovery_metrics", {})
    kwargs.setdefault("config", AirAlertRuleConfig())
    return apply_push_chain(candidates, store=store, config=kwargs.pop("config"), now=now, **kwargs)


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


def test_priority_falls_through_when_higher_rule_gated(tmp_path):
    # 单站规则共享冷却：DS 被防抖拦下时，OL 仍须受同站同因子冷却约束。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    ds_again = _alert(occurred_at="2026-11-02T09:15:00+08:00")
    ds_again["event_id"] = "e-ds-again"
    ol = _alert(rule_type="spatial_outlier", occurred_at="2026-11-02T09:15:00+08:00")
    ol["event_id"] = "e-ol-fresh"
    pushed, suppressed, _summary = _chain(
        [ds_again, ol], store, tmp_path, datetime(2026, 11, 2, 9, 15, tzinfo=TZ)
    )
    assert pushed == []
    assert [(item["alert"]["rule_type"], item["reason"]) for item in suppressed] == [
        ("sudden_rise", "hysteresis"), ("spatial_outlier", "shared_cooldown")
    ]
    state = store.instance("5min", "a", "PM10", "spatial_outlier")
    assert state["armed"] is True and state["last_push_ts"] is None


def test_single_station_rules_share_last_pushed_rule_cooldown(tmp_path):
    # CL-PM10 最后推送，冷却 60 分钟；同站同因子 OL 到 59 分钟仍拦截。
    store = AlertStateStore(tmp_path)
    _chain([_alert(rule_type="continuous_rise")], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    ol = _alert(rule_type="spatial_outlier", occurred_at="2026-11-02T09:59:00+08:00")
    pushed, suppressed, _ = _chain([ol], store, tmp_path, datetime(2026, 11, 2, 9, 59, tzinfo=TZ))
    assert pushed == [] and suppressed[0]["reason"] == "shared_cooldown"

    ol = _alert(rule_type="spatial_outlier", occurred_at="2026-11-02T10:00:00+08:00")
    pushed, suppressed, _ = _chain([ol], store, tmp_path, datetime(2026, 11, 2, 10, 0, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []


def test_single_station_push_does_not_block_multi_station_rise(tmp_path):
    # 单向覆盖（2026-11-25 定版）第一半：单站 DS 推送不读写 MR 规则实例、
    # 不把 MR 纳入单站共享冷却 → 5 分钟后 MR 可立即独立推送（区域事件
    # 不被局部告警压制）。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    regional = _alert(rule_type="multi_station_rise", air_quality_level="轻度污染")
    regional["detail"]["involved_stations"] = [{"station_id": "a"}, {"station_id": "b"}]
    pushed, suppressed, _ = _chain([regional], store, tmp_path, datetime(2026, 11, 2, 9, 5, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    mr_state = store.instance("5min", "a", "PM10", "multi_station_rise")
    assert mr_state["last_push_ts"].startswith("2026-11-02T09:05")
    # 单向覆盖第二半：MR 实际推送后把涉事站（主站+伴随站）同因子的
    # 单站共享冷却组一并置位。
    assert store.notification_group("5min", "a", "PM10")["last_rule_type"] == "multi_station_rise"
    assert store.notification_group("5min", "b", "PM10")["last_event_id"] == "e-a-multi_station_rise-PM10"
    # 未涉事因子组不受影响。
    assert "5min::a::NO2" not in store._load()["notification_groups"]


def test_mr_push_overlays_involved_stations_single_station_cooldown(tmp_path):
    # 单向覆盖第二半：MR 推送后，涉事站同因子的单站告警在 MR 冷却窗口内
    # 不再重复外发同一过程；未涉事站不受影响；窗口过期后恢复正常推送，
    # 组水位翻回实际推送的单站规则。
    store = AlertStateStore(tmp_path)
    mr = _alert(rule_type="multi_station_rise", air_quality_level="轻度污染")
    mr["detail"]["involved_stations"] = [{"station_id": "a"}, {"station_id": "b"}]
    _chain([mr], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))

    ds_b = _alert(station_id="b", occurred_at="2026-11-02T09:30:00+08:00")
    ds_b["event_id"] = "e-b-ds-0930"
    pushed, suppressed, _ = _chain([ds_b], store, tmp_path, datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    assert pushed == [] and suppressed[0]["reason"] == "shared_cooldown"

    # 未涉事站点 c 同刻的 DS 不受 MR 水位影响。
    ds_c = _alert(station_id="c", occurred_at="2026-11-02T09:30:00+08:00")
    ds_c["event_id"] = "e-c-ds-0930"
    pushed_c, suppressed_c, _ = _chain([ds_c], store, tmp_path, datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    assert len(pushed_c) == 1 and suppressed_c == []

    # MR-PM10 冷却 60 分钟：10:01 过期后 DS-b 正常推送，组水位翻回 sudden_rise。
    ds_b2 = _alert(station_id="b", occurred_at="2026-11-02T10:01:00+08:00")
    ds_b2["event_id"] = "e-b-ds-1001"
    pushed2, suppressed2, _ = _chain([ds_b2], store, tmp_path, datetime(2026, 11, 2, 10, 1, tzinfo=TZ))
    assert len(pushed2) == 1 and suppressed2 == []
    assert store.notification_group("5min", "b", "PM10")["last_rule_type"] == "sudden_rise"


def test_mr_watermark_applies_mr_cooldown_window_for_pm25(tmp_path):
    # 生效窗口是 MR 冷却期而非单站规则冷却期：MR-PM2.5 冷却 120 分钟，
    # 90 分钟后（已超出 DS-PM2.5 自身 60 分钟窗口）单站 DS 仍被拦截。
    store = AlertStateStore(tmp_path)
    mr = _alert(rule_type="multi_station_rise", pollutant="PM2.5", grain="1h", air_quality_level="轻度污染")
    mr["event_id"] = "e-mr-pm25"
    mr["detail"]["involved_stations"] = [{"station_id": "a"}]
    _chain([mr], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    ds = _alert(pollutant="PM2.5", grain="1h", occurred_at="2026-11-02T10:30:00+08:00")
    ds["event_id"] = "e-ds-pm25-1030"
    pushed, suppressed, _ = _chain([ds], store, tmp_path, datetime(2026, 11, 2, 10, 30, tzinfo=TZ))
    assert pushed == [] and suppressed[0]["reason"] == "shared_cooldown"

    ds2 = _alert(pollutant="PM2.5", grain="1h", occurred_at="2026-11-02T12:01:00+08:00")
    ds2["event_id"] = "e-ds-pm25-1201"
    pushed2, _suppressed2, _w2 = _chain([ds2], store, tmp_path, datetime(2026, 11, 2, 12, 1, tzinfo=TZ))
    assert len(pushed2) == 1


def test_mr_watermark_lets_level_upgrade_through(tmp_path):
    # 涉事站在 MR 水位冷却内真实恶化（良→轻度污染）：#23 升级例外对共享
    # 冷却同样生效，立即再报，不被区域通报水位静默掉恶化过程。
    store = AlertStateStore(tmp_path)
    mr = _alert(rule_type="multi_station_rise", air_quality_level="良")
    mr["detail"]["involved_stations"] = [{"station_id": "b"}]
    _chain([mr], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    escalated = _alert(
        station_id="b", air_quality_level="轻度污染", occurred_at="2026-11-02T09:30:00+08:00",
    )
    escalated["event_id"] = "e-b-ds-escalated"
    pushed, suppressed, _ = _chain([escalated], store, tmp_path, datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []


def test_upgrade_penetrates_quiet_hours(tmp_path):
    # #23 + 产品定版：夜间（免打扰时段）污染等级升高必须叫人，升级穿透免打扰。
    store = AlertStateStore(tmp_path)
    _chain([_alert(rule_type="spatial_outlier")], store, tmp_path, datetime(2026, 11, 2, 21, 30, tzinfo=TZ))
    escalated = _alert(
        rule_type="spatial_outlier", air_quality_level="轻度污染",
        occurred_at="2026-11-02T23:30:00+08:00",
    )
    escalated["event_id"] = "e-ol-night-upgrade"
    pushed, suppressed, _summary = _chain([escalated], store, tmp_path, datetime(2026, 11, 2, 23, 30, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    assert pushed[0]["is_upgrade"] is True
    assert pushed[0]["upgrade_from_level"] == "良"
    state = store.instance("5min", "a", "PM10", "spatial_outlier")
    assert state["last_air_level"] == "轻度污染"


def test_quiet_hours_still_suppresses_non_upgrade_outlier(tmp_path):
    # 免打扰仍拦常规再报：夜间同级 OL（非升级）照常静默。
    store = AlertStateStore(tmp_path)
    _chain([_alert(rule_type="spatial_outlier")], store, tmp_path, datetime(2026, 11, 2, 21, 30, tzinfo=TZ))
    again = _alert(rule_type="spatial_outlier", occurred_at="2026-11-02T23:30:00+08:00")
    again["event_id"] = "e-ol-night-again"
    pushed, suppressed, _summary = _chain([again], store, tmp_path, datetime(2026, 11, 2, 23, 30, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] == "quiet_hours"


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


def test_mr_quiet_hours_pierces_at_moderate_level(tmp_path):
    # 2026-11-22 定版：轻度及以上的 MR（多站同步抬升）夜间穿透免打扰——
    # 区域事件被静默而未覆盖的单站告警照常外发是口径倒挂（11-22 22:00 实例）。
    store = AlertStateStore(tmp_path)
    night = datetime(2026, 11, 2, 23, 0, tzinfo=TZ)
    pushed, suppressed, _summary = _chain(
        [_alert(rule_type="multi_station_rise", air_quality_level="中度污染")],
        store, tmp_path, night,
    )
    assert len(pushed) == 1 and suppressed == []
    assert pushed[0]["rule_type"] == "multi_station_rise"

    store_light = AlertStateStore(tmp_path / "light")
    pushed_light, _suppressed_light, _w_light = _chain(
        [_alert(rule_type="multi_station_rise", air_quality_level="轻度污染")],
        store_light, tmp_path / "light", night,
    )
    assert len(pushed_light) == 1


def test_mr_quiet_hours_still_suppresses_good_levels_and_outlier(tmp_path):
    # 优/良档 MR 夜间维持静默；mr_quiet_pierce_level_code=0 关闭穿透；
    # spatial_outlier 不享受等级穿透，夜间照旧静默。
    night = datetime(2026, 11, 2, 23, 0, tzinfo=TZ)
    store = AlertStateStore(tmp_path)
    pushed, suppressed, _summary = _chain(
        [_alert(rule_type="multi_station_rise", air_quality_level="良")], store, tmp_path, night,
    )
    assert pushed == [] and suppressed[0]["reason"] == "quiet_hours"

    store_off = AlertStateStore(tmp_path / "pierce-off")
    config = AirAlertRuleConfig(mr_quiet_pierce_level_code=0)
    pushed2, suppressed2, _s2 = _chain(
        [_alert(rule_type="multi_station_rise", air_quality_level="中度污染")],
        store_off, tmp_path / "pierce-off", night, config=config,
    )
    assert pushed2 == [] and suppressed2[0]["reason"] == "quiet_hours"

    store_ol = AlertStateStore(tmp_path / "outlier")
    pushed3, suppressed3, _s3 = _chain(
        [_alert(rule_type="spatial_outlier", air_quality_level="中度污染")],
        store_ol, tmp_path / "outlier", night,
    )
    assert pushed3 == [] and suppressed3[0]["reason"] == "quiet_hours"


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


def test_hysteresis_renotify_after_full_window(tmp_path):
    # 滞回心跳（窗口值=总表冷却期）：未恢复但距上次推送满 30 分钟（DS-PM10）
    # → 强制再报一条持续提醒；心跳后窗口重新计时，期间仍照常滞回抑制。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    again29 = _alert(occurred_at="2026-11-02T09:29:00+08:00")
    again29["event_id"] = "e-again29"
    pushed, suppressed, _summary = _chain([again29], store, tmp_path, datetime(2026, 11, 2, 9, 29, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] == "hysteresis"

    again30 = _alert(occurred_at="2026-11-02T09:30:00+08:00")
    again30["event_id"] = "e-again30"
    pushed, suppressed, _summary = _chain([again30], store, tmp_path, datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    assert len(pushed) == 1 and suppressed == []
    assert pushed[0]["is_renotify"] is True
    assert pushed[0]["renotify_of_event_id"] == "e-a-sudden_rise-PM10"
    assert pushed[0]["renotify_window_minutes"] == 30
    state = store.instance("5min", "a", "PM10", "sudden_rise")
    assert state["armed"] is False
    assert state["first_event_id"] == "e-a-sudden_rise-PM10"

    again59 = _alert(occurred_at="2026-11-02T09:59:00+08:00")
    again59["event_id"] = "e-again59"
    pushed, suppressed, _summary = _chain([again59], store, tmp_path, datetime(2026, 11, 2, 9, 59, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] == "hysteresis"


def test_hysteresis_renotify_still_respects_quiet_hours(tmp_path):
    # 心跳不穿透免打扰：夜间未恢复的 OL 即使满窗口也照常静默。
    store = AlertStateStore(tmp_path)
    _chain([_alert(rule_type="spatial_outlier")], store, tmp_path, datetime(2026, 11, 2, 21, 30, tzinfo=TZ))
    night = _alert(rule_type="spatial_outlier", occurred_at="2026-11-02T23:30:00+08:00")
    night["event_id"] = "e-ol-night-renotify"
    pushed, suppressed, _summary = _chain([night], store, tmp_path, datetime(2026, 11, 2, 23, 30, tzinfo=TZ))
    assert pushed == []
    assert suppressed[0]["reason"] == "quiet_hours"


def test_hysteresis_renotify_can_be_disabled(tmp_path):
    # 运营层开关：hysteresis_renotify=False 回到无上限滞回抑制。
    store = AlertStateStore(tmp_path)
    config = AirAlertRuleConfig()
    config.hysteresis_renotify = False
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    later = _alert(occurred_at="2026-11-02T10:30:00+08:00")
    later["event_id"] = "e-later-1030"
    pushed, suppressed, _summary = _chain(
        [later], store, tmp_path, datetime(2026, 11, 2, 10, 30, tzinfo=TZ), config=config,
    )
    assert pushed == []
    assert suppressed[0]["reason"] == "hysteresis"


def _chronic_store(tmp_path):
    store = AlertStateStore(tmp_path)
    state = store.instance("5min", "a", "CO", "spatial_outlier")
    state["ol_history"] = [
        {"occurred_at": f"2026-11-{19 + index // 2:02d}T0{7 + index % 2}:00:00+08:00",
         "absolute_delta": 0.3}
        for index in range(6)
    ]
    return store, state


def _co_outlier(event_id: str, occurred_at: str, delta: float = 0.3):
    alert = _alert(
        rule_type="spatial_outlier", pollutant="CO", air_quality_level="优",
        occurred_at=occurred_at,
    )
    alert.update(event_id=event_id, absolute_delta=delta)
    return alert


def test_repeated_ol_enters_chronic_state_and_stops_repeat_push(tmp_path):
    store, state = _chronic_store(tmp_path)
    now = datetime(2026, 11, 22, 9, 0, tzinfo=TZ)
    pushed, suppressed, _summary = _chain([_co_outlier("co-new", "2026-11-22T09:00:00+08:00")], store, tmp_path, now)
    assert pushed == [] and suppressed[0]["reason"] == "chronic_outlier"
    assert state["ol_chronic_active"] is True
    assert state["ol_chronic_reference_delta"] == 0.3


def test_chronic_ol_escalates_on_level_or_delta_increase(tmp_path):
    store, _state = _chronic_store(tmp_path)
    now = datetime(2026, 11, 22, 9, 0, tzinfo=TZ)
    _chain([_co_outlier("co-new", "2026-11-22T09:00:00+08:00")], store, tmp_path, now)
    level = _co_outlier("co-level", "2026-11-22T09:30:00+08:00")
    level["air_quality_level"] = "良"
    pushed, _suppressed, _summary = _chain([level], store, tmp_path, datetime(2026, 11, 22, 9, 30, tzinfo=TZ))
    assert pushed[0]["is_upgrade"] is True

    store2, _state2 = _chronic_store(tmp_path / "delta")
    pushed2, _s2, _w2 = _chain(
        [_co_outlier("co-delta", "2026-11-22T09:00:00+08:00", 0.45)],
        store2, tmp_path / "delta", now,
    )
    assert pushed2[0]["chronic_escalation"] is True


def test_chronic_ol_recovers_after_two_quiet_days(tmp_path):
    store, state = _chronic_store(tmp_path)
    _chain([_co_outlier("co-new", "2026-11-22T09:00:00+08:00")], store, tmp_path, datetime(2026, 11, 22, 9, 0, tzinfo=TZ))
    assert state["ol_chronic_active"] is True
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 25, 9, 0, tzinfo=TZ))
    assert state["ol_chronic_active"] is False


def test_state_survives_restart(tmp_path):
    # 重启后从状态文件恢复 armed/冷却期/等级。
    store = AlertStateStore(tmp_path)
    _chain([_alert()], store, tmp_path, datetime(2026, 11, 2, 9, 0, tzinfo=TZ))
    reopened = AlertStateStore(tmp_path)
    state = reopened.instance("5min", "a", "PM10", "sudden_rise")
    assert state["armed"] is False and state["last_air_level"] == "良"
    assert state["first_event_id"] == "e-a-sudden_rise-PM10"
