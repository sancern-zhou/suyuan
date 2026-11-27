"""②企业核查线索周报单元测试：episode 汇总、筛查聚合、兜底周报。"""

from __future__ import annotations

from app.fetchers import xuchang_enterprise_clue_weekly as weekly
from app.scenarios.xuchang_enterprise_clue import notification


def _episode(station_id="1008A", station_name="许昌学院", pollutant="PM10",
             started="2026-11-04T10:00:00", peak=200.0):
    return {
        "station_id": station_id, "station_name": station_name,
        "target_pollutant": pollutant, "alert_type": "sudden_rise",
        "started_at": started, "peak_station_value": peak,
    }


def test_summarize_episodes():
    summary = weekly.summarize_episodes([
        _episode(), _episode(started="2026-11-05T09:00:00"),
        _episode(station_id="1003A", station_name="开发区", pollutant="SO2"),
    ])
    assert summary["episode_count"] == 3
    assert summary["station_count"] == 2
    assert summary["by_station"][0] == {"name": "许昌学院", "count": 2}
    assert summary["by_pollutant"][0] == {"name": "PM10", "count": 2}


def test_station_meta_for_matches_id_and_name():
    meta = weekly.station_meta_for(_episode(station_id="1008A"))
    assert meta and meta["name"] == "许昌学院" and meta["lon"] > 113
    meta_by_name = weekly.station_meta_for(_episode(station_id="unknown"))
    assert meta_by_name and meta_by_name["station_id"] == "1008A"
    assert weekly.station_meta_for(_episode(station_id="?", station_name="不存在站")) is None


def test_screen_week_candidates_merges_hits(tmp_path, monkeypatch):
    calls: list[dict] = []

    def _fake_screen(**kwargs):
        calls.append(kwargs)
        return {
            "status": "screened",
            "wind": {"status": "available", "direction_from_deg": 225.0},
            "enterprises": [
                {"enterprise_name": "企业A", "district": "魏都区",
                 "industry_category": "铸造", "screening_score": 99.0,
                 "distance_km": 3.2, "in_upwind_sector": True},
                {"enterprise_name": "企业B", "district": "建安区",
                 "industry_category": "涂装", "screening_score": 50.0,
                 "distance_km": 8.0, "in_upwind_sector": False},
            ],
        }

    monkeypatch.setattr(weekly, "screen_inventory_candidates", _fake_screen)
    result = weekly.screen_week_candidates(
        [_episode(), _episode(started="2026-11-05T09:00:00"),
         _episode(station_id="1003A", station_name="开发区", pollutant="SO2")],
        [{"time": "2026-11-04T10:00:00", "wind_direction_10m": 225.0,
          "wind_speed_10m_ms": 3.0}],
    )
    assert result["status"] == "screened"
    # SO2 不在清单筛查口径（ANNUAL_EMISSION_FIELD 仅 PM2.5/PM10/O3/NOX）→ 只筛 1 组
    assert len(calls) == 1
    # 企业A 上风向命中两次（同站两次 episode），企业B 不在上风向不计数
    assert len(result["frequent_candidates"]) == 1
    top = result["frequent_candidates"][0]
    assert top["enterprise_name"] == "企业A"
    assert top["hit_count"] == 2
    assert top["stations"] == ["许昌学院"]
    assert result["district_distribution"] == [{"name": "魏都区", "count": 2}]
    station_report = result["station_reports"][0]
    assert station_report["station_name"] == "许昌学院"
    assert station_report["episode_count"] == 2


def test_screen_week_candidates_no_episodes():
    result = weekly.screen_week_candidates([], [])
    assert result["status"] == "not_run"
    assert result["frequent_candidates"] == []


def test_compose_fallback_message_lists_candidates_and_boundaries():
    evidence = {
        "window": {"start": "2026-11-04", "end": "2026-11-11"},
        "episodes": {"episode_count": 3, "station_count": 2,
                     "by_station": [{"name": "许昌学院", "count": 2}]},
        "enterprise_screening": {
            "status": "screened",
            "frequent_candidates": [
                {"enterprise_name": "企业A", "district": "魏都区",
                 "hit_count": 2, "best_distance_km": 3.2},
            ],
            "district_distribution": [{"name": "魏都区", "count": 2}],
        },
    }
    message = notification.compose_fallback_message(evidence)
    assert message.startswith("【企业核查线索周报】")
    assert "3个" in message
    assert "企业A" in message
    assert "魏都区" in message
    assert "不认定" in message or "不代表" in message


def test_compose_fallback_message_no_alerts():
    evidence = {
        "window": {"start": "2026-11-04", "end": "2026-11-11"},
        "episodes": {"episode_count": 0, "station_count": 0},
        "enterprise_screening": {"status": "not_run", "frequent_candidates": []},
    }
    message = notification.compose_fallback_message(evidence)
    assert "无站点快速告警记录" in message
    assert "无符合条件的筛查对象" in message
