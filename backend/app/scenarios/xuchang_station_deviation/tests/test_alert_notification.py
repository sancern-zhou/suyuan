"""Tests for the deterministic station-alert notification workflow.

推送文案为 6 条目紧凑格式（【浓度告警】+ 编号条目），全部由代码从证据包
确定性渲染，不再经 LLM 生成。
"""

import asyncio
import json

import pytest

from app.scenarios.xuchang_station_deviation.alert_notification import (
    _collect_media,
    compose_station_alert_fallback_message,
    compose_station_alert_message,
    run_station_alert_workflow,
)


def _deviation_alert(**overrides) -> dict:
    alert = {
        "event_id": "xuchang-station-deviation-202609131200-no2",
        "occurred_at": "2026-09-13T12:00:00+08:00",
        "station_id": "1003A",
        "station_name": "开发区",
        "target_pollutant": "NO2",
        "measurement_granularity": "5min",
        "observed_indicator": "NO2",
        "station_value": 35.0,
        "peer_mean": 19.4,
        "absolute_delta": 15.6,
        "deviation_percent": 80.4,
        "peer_station_count": 5,
        "rule": "relative_deviation > threshold AND absolute_delta > pollutant_absolute_threshold",
        "pollutant_source_features": {
            "status": "calculated",
            "classification": "偏燃烧型",
            "components": {"PM2.5": 0.42, "SO2": 0.31, "NO2": 0.12},
        },
    }
    alert.update(overrides)
    return alert


def _deviation_evidence(**overrides) -> dict:
    evidence = {
        "observed_meteorology": {
            "status": "success",
            "station_hour_records": [
                {
                    "time": "2026-09-13T01:00:00+00:00",
                    "station_name": "许昌",
                    "wind_direction_10m": 68.0,
                    "wind_speed_10m": 3.0,
                    "temperature_2m": 28.7,
                    "relative_humidity_2m": 56.0,
                },
                {
                    "time": "2026-09-13T02:00:00+00:00",
                    "station_name": "许昌",
                    "wind_direction_10m": 213.0,
                    "wind_speed_10m": 0.8,
                    "temperature_2m": 22.2,
                    "relative_humidity_2m": 77.0,
                },
            ],
        },
        "air_quality_context": {"maintenance_qc_review": None},
        "computed_indicators": {
            "station_5min_process": {
                "status": "success",
                "target_station_values": [
                    {"time": "2026-09-13T11:00:00+08:00", "value": 26.0},
                    {"time": "2026-09-13T12:00:00+08:00", "value": 35.0},
                ],
            },
            "station_process": {"status": "unavailable"},
        },
        "dispatch_media": [],
    }
    evidence.update(overrides)
    return evidence


def _package(alerts: list[dict], media: list[str] | None = None) -> dict:
    return {
        "schema_version": "xuchang_station_deviation_episode_evidence/v1",
        "station_id": alerts[0]["alert"]["station_id"],
        "occurred_at": alerts[0]["alert"]["occurred_at"],
        "alerts": alerts,
        "dispatch_media": media or [],
    }


def test_compose_deviation_notification_compact_six_items():
    message = compose_station_alert_message(_package([
        {"alert": _deviation_alert(), "evidence": _deviation_evidence()},
    ]))
    lines = message.splitlines()

    assert lines[0] == "【浓度告警】1.告警站点：开发区"
    assert lines[1] == "2.告警时间：2026年09月13日12:00"
    assert lines[2] == "3.污染指标：NO2"
    assert lines[3] == (
        "4.告警情况：开发区实测35.0微克/立方米，周边5站均值19.4，"
        "绝对偏差15.6，相对偏差80.4%"
    )
    assert lines[4] == "5.气象情况：温度22.2℃，相对湿度77%，西南偏南风，风速0.8米/秒"
    assert lines[5] == "6.质控关联：前一小时内无质控记录"
    # 观测时间必须换算为本地时区且取告警前最近一条（213° 那条而非更早的 68°）
    assert "东北偏东风" not in message
    assert "backend/" not in message  # 不暴露本地路径


def test_compose_rise_notification_uses_rise_indicators():
    alert = _deviation_alert(
        target_pollutant="PM10",
        station_value=180.0,
        rise_window_values=[120.0, 135.0, 150.0, 158.0, 166.0, 172.0, 180.0],
        total_rise_abs=60.0,
        total_rise_rate=0.5,
        rule="six_consecutive_5min_rises_and_pollutant_thresholds",
    )
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))

    assert "4.告警情况：开发区实测180.0微克/立方米，30分钟内从120.0连续6个5分钟节抬升至180.0" in message
    assert "累计抬升60.0（累计涨幅50.0%）" in message


def test_hour_granularity_appends_to_pollutant_line():
    alert = _deviation_alert(
        measurement_granularity="hour",
        rise_window_values=[20.0, 26.0, 35.0],
        rule="six_consecutive_hourly_rises_and_pollutant_thresholds",
    )
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))

    assert "3.污染指标：NO2（小时数据）" in message
    assert "从20.0连续2个小时节抬升至35.0" in message


def test_upgrade_alert_prefixed_in_fact_sentence():
    alert = _deviation_alert(is_upgrade=True)
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))

    assert "4.告警情况：【升级】开发区实测35.0微克/立方米" in message
    assert message.splitlines()[0] == "【浓度告警】1.告警站点：开发区"


def test_renotify_alert_prefixed_in_fact_sentence():
    # 滞回心跳的持续提醒：站名前加【持续】标记，区别于新事件。
    alert = _deviation_alert(is_renotify=True)
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))

    assert "4.告警情况：【持续】开发区实测35.0微克/立方米" in message


def test_multi_factor_episode_merges_into_one_notice():
    pm10 = _deviation_alert(
        target_pollutant="PM10",
        station_value=180.0,
        pollutant_source_features={"status": "not_calculated"},
    )
    no2 = _deviation_alert()
    message = compose_station_alert_message(_package([
        {"alert": pm10, "evidence": _deviation_evidence()},
        {"alert": no2, "evidence": _deviation_evidence()},
    ]))
    lines = message.splitlines()

    assert lines[0] == "【浓度告警】1.告警站点：开发区"
    assert lines[2] == "3.污染指标：PM10、NO2"
    # 气象与质控只出现一次
    assert sum(1 for line in lines if line.startswith("5.气象情况")) == 1
    assert sum(1 for line in lines if line.startswith("6.质控关联")) == 1
    assert "开发区实测180.0微克/立方米" in message
    assert "开发区实测35.0微克/立方米" in message


def test_region_merged_alerts_listed_in_notice():
    primary = _deviation_alert(
        target_pollutant="PM25",
        station_value=95.0,
        rule="six_consecutive_hourly_rises_and_pollutant_thresholds",
        detail={
            "region_stations": [
                {"station_id": "1005A", "station_name": "文教园区", "station_value": 88.0},
                {"station_id": "1008A", "station_name": "椹涧乡", "station_value": 82.0},
            ]
        },
    )
    message = compose_station_alert_message(_package([
        {"alert": primary, "evidence": _deviation_evidence()},
    ]))
    lines = message.splitlines()

    assert lines[0] == "【浓度告警】1.告警站点：开发区，文教园区，椹涧乡"
    assert "文教园区实测88.0微克/立方米" in message
    assert "椹涧乡实测82.0微克/立方米" in message


def test_region_merged_sudden_rise_facts():
    # DS 区域合并：合并站带基线抬升信息，逐站事实句分号衔接。
    primary = _deviation_alert(
        target_pollutant="PM25",
        station_value=57.0,
        rule_type="sudden_rise",
        rule="sudden_rise",
        rule_label="单点突升",
        detail={
            "baseline": 40.0,
            "delta": 17.0,
            "region_stations": [
                {
                    "station_id": "1012A", "station_name": "望田路111号",
                    "station_value": 55.0, "delta": 15.0, "baseline": 40.0,
                },
            ],
        },
    )
    message = compose_station_alert_message(_package([
        {"alert": primary, "evidence": _deviation_evidence()},
    ]))

    assert "4.告警情况：开发区实测57.0微克/立方米，较近段基线40.0抬升17.0；" in message
    assert "望田路111号实测55.0微克/立方米，较近段基线40.0抬升15.0" in message


def test_multi_station_rise_facts():
    # MR 多站同步抬升：主站事实 + 共N站口径 + 覆盖说明；其余站进区域清单句。
    alert = _deviation_alert(
        target_pollutant="PM10",
        station_id="1005A",
        station_name="市一中",
        station_value=38.0,
        rule_type="multi_station_rise",
        rule="multi_station_rise",
        rule_label="多站同步抬升",
        detail={
            "path": "co_deviation",
            "involved_stations": [
                {"station_id": "1005A", "station_name": "市一中", "station_value": 38.0,
                 "peer_mean": 25.0, "delta": 13.0, "threshold": 12.5},
                {"station_id": "1012A", "station_name": "望田路111号", "station_value": 37.0,
                 "peer_mean": 25.2, "delta": 11.8, "threshold": 12.6},
            ],
            "region_stations": [
                {"station_id": "1012A", "station_name": "望田路111号", "station_value": 37.0,
                 "peer_mean": 25.2, "delta": 11.8},
            ],
            "mr_tier": "push",
        },
    )
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))
    lines = message.splitlines()

    assert lines[0] == "【浓度告警】1.告警站点：市一中，望田路111号"
    assert "市一中实测38.0微克/立方米，周边站均值25.0，偏高13.0" in message
    assert "共2站一致偏高，已覆盖涉事站点单站告警" in message
    assert "望田路111号实测37.0微克/立方米" in message

    # 非区域合并告警不出现合并站
    plain = compose_station_alert_message(_package([
        {"alert": _deviation_alert(), "evidence": _deviation_evidence()},
    ]))
    assert "望田路111号" not in plain


def test_fallback_message_matches_main_renderer():
    package = _package([{"alert": _deviation_alert(), "evidence": _deviation_evidence()}])

    assert compose_station_alert_fallback_message(package) == compose_station_alert_message(package)


def test_missing_meteorology_and_qc_marks_rendered_honestly():
    evidence = _deviation_evidence(
        observed_meteorology={"status": "unavailable", "station_hour_records": []},
    )
    evidence["computed_indicators"]["station_5min_process"]["marked_quality_records"] = [
        {"time": "2026-09-13T11:55:00+08:00", "station_id": "1003A", "mark": "质控"},
        {"time": "2026-09-13T12:00:00+08:00", "station_id": "1003A", "mark": "零校准"},
    ]
    message = compose_station_alert_message(_package([
        {"alert": _deviation_alert(), "evidence": evidence},
    ]))

    assert "5.气象情况：暂无可用气象观测" in message
    assert "6.质控关联：前一小时内存在2条带质控标记的监测记录" in message


def test_maintenance_qc_review_takes_priority():
    evidence = _deviation_evidence(
        air_quality_context={
            "maintenance_qc_review": {
                "required": True,
                "records": [{"time": "2026-09-13T12:00:00+08:00", "marks": {"pm10_mark": "质控"}}],
                "instruction": "存在质控标记",
            }
        },
    )
    message = compose_station_alert_message(_package([
        {"alert": _deviation_alert(), "evidence": evidence},
    ]))

    assert "6.质控关联：前一小时内存在1条质控标记记录，相关时段数据受运维质控影响" in message


def test_collect_media_deduplicates_and_keeps_existing_files(tmp_path):
    existing = tmp_path / "chart.png"
    existing.write_bytes(b"png")
    package = _package(
        [
            {
                "alert": {**_deviation_alert(), "dispatch_media": [str(existing), "/missing/a.png"]},
                "evidence": {"dispatch_media": [str(existing)]},
            }
        ],
        media=[str(existing), "/missing/b.png"],
    )

    assert _collect_media(package) == [str(existing)]


def test_run_station_alert_workflow_delivers_composed_notice(tmp_path, monkeypatch):
    evidence_path = tmp_path / "episode.evidence.json"
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    package = _package(
        [{"alert": _deviation_alert(), "evidence": _deviation_evidence()}],
        media=[str(chart)],
    )
    evidence_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")

    delivered = {}

    class _FakeDelivery:
        async def resolve_recipients(self, user_ids):
            delivered["user_ids"] = list(user_ids)
            return [{"user_id": user_ids[0], "social_user_id": user_ids[0], "name": "android_demo"}]

        async def deliver(self, *, task, event, execution, output, recipients):
            delivered["message"] = output.broadcast.message
            delivered["media"] = output.broadcast.media
            delivered["recipients"] = recipients
            return [{"user_id": recipients[0]["user_id"], "sent": True}]

    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.alert_notification.EventTaskDelivery",
        _FakeDelivery,
    )
    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.wechat_push_queue.get_data_registry",
        lambda: tmp_path,
    )

    from types import SimpleNamespace

    task = SimpleNamespace(
        target_user_ids=["app:android:android_demo"],
        prompt="执行指令测试",
    )
    execution = SimpleNamespace(execution_id="exec-1")
    event = SimpleNamespace(payload={"evidence_package_path": str(evidence_path)})

    result = asyncio.run(run_station_alert_workflow(task=task, execution=execution, event=event))

    expected_message = compose_station_alert_message(package)
    assert delivered["user_ids"] == ["app:android:android_demo"]
    assert delivered["message"] == expected_message
    assert delivered["message"].startswith("【浓度告警】")
    assert delivered["media"] == [str(chart)]
    assert "投递成功1个" in result["summary"]
    assert result["final_message"] == expected_message
    assert result["tool_call_details"]["media_count"] == 1

    # 文案定稿后同步入队微信群推送队列
    from app.scenarios.xuchang_station_deviation import wechat_push_queue

    pending = wechat_push_queue.list_pending_messages(root=tmp_path)
    assert len(pending) == 1
    assert pending[0]["text"] == expected_message


def test_run_station_alert_workflow_requires_evidence_path():
    from types import SimpleNamespace

    task = SimpleNamespace(target_user_ids=["app:android:android_demo"])
    event = SimpleNamespace(payload={})

    with pytest.raises(RuntimeError, match="evidence_package_path"):
        asyncio.run(run_station_alert_workflow(task=task, execution=SimpleNamespace(), event=event))
