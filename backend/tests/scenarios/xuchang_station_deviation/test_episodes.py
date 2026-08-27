from datetime import datetime
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


def test_episode_suppresses_repeated_hours_and_reanalyzes_material_worsening(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)

    started = service.record(_alert(10, 100, 0.8))
    suppressed = service.record(_alert(11, 105, 0.85))
    worsening = service.record(_alert(12, 130, 1.1))

    assert started["should_analyze"] is True
    assert suppressed["status"] == "suppressed_update"
    assert suppressed["should_analyze"] is False
    assert worsening["status"] == "material_update"
    assert worsening["should_analyze"] is True
    assert worsening["episode"]["notification_count"] == 2


def test_episode_closes_after_three_hours_without_deviation(tmp_path):
    service = XuchangStationDeviationEpisodeService(output_root=tmp_path)
    service.record(_alert(10, 100, 0.8))

    closed = service.close_stale(datetime(2026, 8, 5, 13, tzinfo=TZ_SHANGHAI))

    assert len(closed) == 1
    assert closed[0]["status"] == "closed"
    assert service.close_stale(datetime(2026, 8, 5, 14, tzinfo=TZ_SHANGHAI)) == []
