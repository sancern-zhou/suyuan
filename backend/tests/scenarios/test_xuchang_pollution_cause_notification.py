"""④污染原因分析通报工作流兜底模板单元测试。"""

from __future__ import annotations

from app.scenarios.xuchang_pollution_cause import notification


def _evidence(**overrides):
    evidence = {
        "city": "许昌市",
        "target_date": "2026-11-10",
        "rule_description": "许昌市PM2.5日均浓度高于相邻五市均值20%以上",
        "ratio_threshold": 0.20,
        "neighbor_cities": ["郑州市", "开封市", "平顶山市", "漯河市", "周口市"],
        "xuchang_pm25": 96.0,
        "neighbor_mean_pm25": 74.0,
        "deviation_percent": 29.7,
        "triggered": True,
        "streak_days": 2,
        "city_rank": 14,
        "city_count": 18,
        "city_rows": [
            {"city": "许昌市", "pm25": 96.0, "is_neighbor": False, "is_xuchang": True},
            {"city": "郑州市", "pm25": 80.0, "is_neighbor": True, "is_xuchang": False},
            {"city": "周口市", "pm25": 80.0, "is_neighbor": True, "is_xuchang": False},
        ],
    }
    evidence.update(overrides)
    return evidence


def test_fallback_message_sections_and_numbers(tmp_path, monkeypatch):
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module,
        "load_review_manifest",
        lambda target_date: {
            "episode_count": 2,
            "alert_list": [{"station_name": "许昌学院"}, {"station_name": "开发区"}],
            "meteorology_intervals": {
                "nmc": {
                    "valid_hours": 24,
                    "temperature_2m": {"min": 10.0, "max": 20.0},
                    "relative_humidity_2m": {"mean": 75.0},
                    "wind_speed_10m": {"mean": 1.8},
                    "precipitation": {"sum": 0.0},
                }
            },
        },
    )
    message = notification.compose_fallback_message(_evidence())
    assert message.startswith("【污染原因分析】")
    for section in ("一、触发情况", "二、区域对比", "三、气象概况",
                    "四、站点告警情况", "五、关注建议"):
        assert section in message
    assert "29.7%" in message
    assert "连续2天" in message
    assert "第14位" in message
    assert "郑州市80.0" in message
    assert "2个" in message
    assert "不认定" in message


def test_fallback_message_without_review_manifest(tmp_path, monkeypatch):
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module, "load_review_manifest", lambda target_date: None
    )
    message = notification.compose_fallback_message(_evidence())
    assert "气象观测数据暂缺" in message
    assert "无站点快速告警记录" in message


def test_build_llm_evidence_folds_review():
    evidence = _evidence()
    manifest = {"episode_count": 3, "meteorology_intervals": {"nmc": {"valid_hours": 20}}}
    payload = notification.build_llm_evidence(evidence, manifest)
    assert payload["trigger_evidence"]["deviation_percent"] == 29.7
    assert payload["daily_review"]["episode_count"] == 3
    assert "meteorology_intervals" in payload["daily_review"]
    assert len(payload["city_rows"]) == 3

    payload_empty = notification.build_llm_evidence(evidence, None)
    assert "daily_review" not in payload_empty
