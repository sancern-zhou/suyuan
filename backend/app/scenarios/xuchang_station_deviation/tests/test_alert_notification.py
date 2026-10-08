"""Tests for the deterministic station-alert notification workflow."""

import asyncio
import json

import pytest

from app.scenarios.xuchang_station_deviation.alert_notification import (
    _collect_media,
    compose_station_alert_message,
    run_station_alert_workflow,
)


def _deviation_alert(**overrides) -> dict:
    alert = {
        "event_id": "xuchang-station-deviation-202609131200-nox",
        "occurred_at": "2026-09-13T12:00:00+08:00",
        "station_id": "1003A",
        "station_name": "开发区",
        "target_pollutant": "NOX",
        "measurement_granularity": "5min",
        "observed_indicator": "NO2",
        "nox_proxy_note": "NO2站点小时浓度作为NOX空间异常筛查代理",
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


def test_compose_deviation_notification_covers_all_sections():
    package = _package([
        {"alert": _deviation_alert(), "evidence": _deviation_evidence()},
    ])

    message = compose_station_alert_message(package)

    assert message.startswith("【许昌站点污染抬升告警｜开发区｜NOX】")
    for section in ("一、告警概况", "二、监测趋势", "三、气象与质控", "四、污染特征", "五、调度指令"):
        assert section in message
    assert "单站相对区域偏高" in message
    assert "均值19.4" in message
    assert "相对偏高80.4%" in message
    # 观测时间必须换算为本地时区（02:00Z -> 10:00+08），且使用告警前最近一条
    assert "2026-09-13 10:00观测" in message
    assert "风来东东北方向（68°）" not in message  # 必须选 213° 那条而非更早记录
    assert "南西南方向（213°）" in message
    assert "NO2站点小时浓度作为NOX空间异常筛查代理" in message
    assert "拥堵、怠速、机械和燃烧" in message
    assert "不作为来源认定或同步上升证据" in message
    assert "backend/" not in message  # 不暴露本地路径


def test_compose_rise_notification_uses_rise_indicators():
    alert = _deviation_alert(
        target_pollutant="PM10",
        nox_proxy_note=None,
        measurement_granularity="5min",
        station_value=180.0,
        rise_window_values=[120.0, 135.0, 150.0, 158.0, 166.0, 172.0, 180.0],
        total_rise_abs=60.0,
        total_rise_rate=0.5,
        rule="six_consecutive_5min_rises_and_pollutant_thresholds",
        pollutant_source_features={"status": "not_calculated"},
    )
    message = compose_station_alert_message(_package([
        {"alert": alert, "evidence": _deviation_evidence()},
    ]))

    assert "单站持续快速上升" in message
    assert "从120连续6个5分钟节抬升至180" in message
    assert "累计抬升60" in message and "累计涨幅50%" in message
    assert "本次未计算污染组成特征" in message
    assert "检查站点周边积尘、带泥和运输抛撒" in message


def test_multi_factor_episode_merges_into_one_notice(tmp_path):
    pm10 = _deviation_alert(
        target_pollutant="PM10",
        nox_proxy_note=None,
        station_value=180.0,
        rule="relative_deviation > threshold AND absolute_delta > pollutant_absolute_threshold",
        pollutant_source_features={"status": "not_calculated"},
        upwind_road_scope_image_path=None,
    )
    nox = _deviation_alert()
    message = compose_station_alert_message(_package([
        {"alert": pm10, "evidence": _deviation_evidence()},
        {"alert": nox, "evidence": _deviation_evidence()},
    ]))

    assert "【许昌站点污染抬升告警｜开发区｜PM10、NOX】" in message
    assert "合并为一条通报" in message
    assert message.count("三、气象与质控") == 1  # 气象与质控只出现一次
    assert "自行核实周边3公里范围" in message  # PM10 地图缺失时如实说明
    assert "NO2站点小时浓度作为NOX空间异常筛查代理" in message


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

    async def _fake_chat(messages, **kwargs):
        assert messages[0]["role"] == "user"
        assert "可信证据包" in messages[0]["content"]
        assert '"alerts"' in messages[0]["content"]
        assert "执行指令测试" in messages[0]["content"]
        return {"content": [{"type": "text", "text": "LLM 生成的站点告警通报"}]}

    monkeypatch.setattr(
        "app.services.llm_service.llm_service.chat_anthropic",
        _fake_chat,
    )

    from types import SimpleNamespace

    task = SimpleNamespace(
        target_user_ids=["app:android:android_demo"],
        prompt="执行指令测试",
    )
    execution = SimpleNamespace(execution_id="exec-1")
    event = SimpleNamespace(payload={"evidence_package_path": str(evidence_path)})

    result = asyncio.run(run_station_alert_workflow(task=task, execution=execution, event=event))

    assert delivered["user_ids"] == ["app:android:android_demo"]
    assert delivered["message"] == "LLM 生成的站点告警通报"
    assert delivered["media"] == [str(chart)]
    assert "投递成功1个" in result["summary"]
    assert result["tool_call_details"]["media_count"] == 1


def test_run_station_alert_workflow_requires_evidence_path():
    from types import SimpleNamespace

    task = SimpleNamespace(target_user_ids=["app:android:android_demo"])
    event = SimpleNamespace(payload={})

    with pytest.raises(RuntimeError, match="evidence_package_path"):
        asyncio.run(run_station_alert_workflow(task=task, execution=SimpleNamespace(), event=event))
