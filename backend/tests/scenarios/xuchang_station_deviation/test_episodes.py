from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_station_deviation.episodes import (
    XuchangStationDeviationEpisodeService,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _alert(hour: int, value: float, ratio: float) -> dict:
    return {
        "event_id": f"alert-{hour}",
        "occurred_at": datetime(2026, 8, 5, hour, tzinfo=TZ_SHANGHAI).isoformat(),
        "city": "许昌市",
        "station_id": "XC001",
        "station_name": "测试站",
        "target_pollutant": "PM2.5",
        "station_value": value,
        "deviation_ratio": ratio,
    }


def _minute_alert(minutes: int, value: float, ratio: float) -> dict:
    alert = _alert(10, value, ratio)
    alert["event_id"] = f"alert-minute-{minutes}"
    alert["occurred_at"] = (
        datetime(2026, 8, 5, 10, tzinfo=TZ_SHANGHAI) + timedelta(minutes=minutes)
    ).isoformat()
    alert["measurement_granularity"] = "5min"
    return alert


def test_episode_hard_cooldown_then_requires_new_peak_increase(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)

    started = service.record(_minute_alert(0, 100, 0.8))
    early_worsening = service.record(_minute_alert(5, 130, 1.2))
    early_peak = service.record(_minute_alert(25, 160, 1.5))
    insufficient = service.record(_minute_alert(30, 200, 1.74))
    worsening = service.record(_minute_alert(35, 205, 1.99))

    assert started["should_analyze"] is True
    assert early_worsening["status"] == "suppressed_update"
    assert early_worsening["reason"] == "notification_cooldown"
    assert early_peak["should_analyze"] is False
    assert early_peak["episode"]["peak_deviation_ratio"] == 1.5
    assert insufficient["should_analyze"] is False
    assert insufficient["episode"]["last_notified_at"] == started["episode"]["last_notified_at"]
    assert worsening["status"] == "material_update"
    assert worsening["should_analyze"] is True
    assert worsening["episode"]["notification_count"] == 2


def test_episode_notifies_at_60_minutes_and_restarts_cooldown(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)
    service.record(_minute_alert(0, 100, 0.8))
    for minute in range(5, 60, 5):
        assert service.record(_minute_alert(minute, 100, 0.8))["should_analyze"] is False

    reminder = service.record(_minute_alert(60, 100, 0.8))
    assert reminder["status"] == "reminder"
    assert reminder["reason"] == "notification_window_elapsed"
    assert reminder["episode"]["notification_count"] == 2
    assert service.record(_minute_alert(65, 150, 1.5))["should_analyze"] is False
    worsening = service.record(_minute_alert(90, 150, 1.75))
    assert worsening["status"] == "material_update"
    assert worsening["episode"]["notification_count"] == 3


def test_episode_does_not_close_during_notification_window(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)
    started = service.record(_minute_alert(0, 100, 0.8))

    assert service.close_stale(datetime(2026, 8, 5, 10, 30, tzinfo=TZ_SHANGHAI)) == []
    repeated = service.record(_minute_alert(35, 105, 0.8))
    assert repeated["should_analyze"] is False
    assert repeated["episode"]["episode_id"] == started["episode"]["episode_id"]
    closed = service.close_stale(datetime(2026, 8, 5, 11, 5, tzinfo=TZ_SHANGHAI))
    assert len(closed) == 1
    assert closed[0]["notification_count"] == 1


def test_episode_closes_after_three_hours_without_deviation(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)
    service.record(_alert(10, 100, 0.8))

    closed = service.close_stale(datetime(2026, 8, 5, 13, tzinfo=TZ_SHANGHAI))

    assert len(closed) == 1
    assert closed[0]["status"] == "closed"
    assert service.close_stale(datetime(2026, 8, 5, 14, tzinfo=TZ_SHANGHAI)) == []
