from datetime import datetime

from app.scenarios.xuchang_daily_review.map_frames import build_pollutant_map_frames
from app.scenarios.xuchang_daily_review.report_events import build_report_events


def _analysis(episode_id, station_id, start, end=None, pollutant="PM10"):
    return {
        "episode_id": episode_id,
        "alert_anchor": {"station_id": station_id, "station_name": station_id,
                         "target_pollutant": pollutant, "episode_start": f"2026-09-25T{start:02d}:00:00",
                         "episode_end": f"2026-09-25T{(end or start):02d}:00:00"},
        "target_response": {"lat": 34.0, "lon": 113.8},
    }


def _row(station_id, hour, value, lat, lon, station_type="regular"):
    return {"station_id": station_id, "name": station_id, "station_type": station_type,
            "data_time": datetime(2026, 9, 25, hour), "pm10": value, "lat": lat, "lon": lon}


def test_one_unalerted_hour_merges_but_retains_segments_and_map_gap():
    analyses = [
        _analysis("a", "target", 10), _analysis("b", "target", 11),
        _analysis("c", "target", 13), _analysis("d", "other", 11),
    ]
    regular = [_row("target", h, v, 34.0, 113.8) for h, v in
               ((9, 10), (10, 20), (11, 30), (12, 25), (13, 40))]
    regular += [_row("other", 10, 12, 34.05, 113.85),
                _row("other", 11, 18, 34.05, 113.85)]
    township = [_row("north", h, v, 34.1, 113.8, "township") for h, v in ((10, 35), (11, 45))]
    township += [_row("south", h, 80, 33.9, 113.8, "township") for h in (10, 11)]
    weather = [{"time": f"2026-09-25T{h:02d}:00:00+08:00", "wind_speed_10m": 2,
                "wind_direction_10m": 0} for h in (10, 11)]

    evidence = build_report_events(analyses, regular, township, weather)
    assert evidence["event_count"] == 2
    merged = next(event for event in evidence["events"] if event["source_episode_ids"] == ["a", "b", "c"])
    assert merged["start_time"] == "2026-09-25T10:00:00"
    assert merged["end_time"] == "2026-09-25T13:00:00"
    assert merged["reference_time"] == "2026-09-25T09:00:00"
    assert merged["peak_rise_absolute"] == 30
    assert merged["peak_rise_percent"] == 300
    assert merged["alert_hour_count"] == 3
    assert merged["gap_hour_count"] == 1
    assert [(part["start_time"], part["end_time"]) for part in merged["alert_intervals"]] == [
        ("2026-09-25T10:00:00", "2026-09-25T11:00:00"),
        ("2026-09-25T13:00:00", "2026-09-25T13:00:00"),
    ]
    assert [part["peak_rise_absolute"] for part in merged["segments"]] == [20, 15]
    assert [part["wind"]["status"] for part in merged["segments"]] == ["ok", "insufficient_data"]
    assert merged["wind"]["direction_name"] == "北"
    assert [station["station_id"] for station in merged["upwind_township_stations"]] == ["north"]
    assert merged["upwind_township_stations"][0]["concentration_mean"] == 40
    assert merged["upwind_township_stations"][0]["vs_target"] == "高于"

    maps = build_pollutant_map_frames(evidence["events"], regular, township, "2026-09-25")
    assert maps["pollutant_count"] == 1
    assert len(maps["maps"][0]["frames"]) == 24
    assert maps["maps"][0]["frames"][10]["active_event_ids"] == [merged["event_id"]]
    assert maps["maps"][0]["frames"][12]["active_event_ids"] == []
    assert maps["maps"][0]["frames"][13]["active_event_ids"] == [merged["event_id"]]
    assert len(maps["maps"][0]["frames"][10]["records"]) == 4


def test_longer_gap_and_different_pollutant_remain_separate():
    result = build_report_events([
        _analysis("a", "target", 10), _analysis("b", "target", 13),
        _analysis("c", "target", 11, pollutant="PM2.5"),
    ], [], [], [])
    assert result["event_count"] == 3


def test_missing_wind_has_no_upwind_claim():
    result = build_report_events([_analysis("a", "target", 10)],
                                 [_row("target", 10, 20, 34.0, 113.8)],
                                 [_row("north", 10, 30, 34.1, 113.8, "township")], [])
    assert result["events"][0]["wind"]["status"] == "insufficient_data"
    assert result["events"][0]["upwind_township_stations"] == []


def test_neighbor_comparison_uses_only_hours_with_both_observations():
    result = build_report_events(
        [_analysis("a", "target", 10, 11)],
        [_row("target", 10, 20, 34.0, 113.8)],
        [_row("north", 10, 10, 34.1, 113.8, "township"),
         _row("north", 11, 100, 34.1, 113.8, "township")],
        [{"time": f"2026-09-25T{hour:02d}:00:00+08:00",
          "wind_speed_10m": 2, "wind_direction_10m": 0} for hour in (10, 11)],
    )
    neighbor = result["events"][0]["upwind_township_stations"][0]
    assert neighbor["concentration_mean"] == 55
    assert neighbor["comparison_concentration_mean"] == 10
    assert neighbor["target_comparison_mean"] == 20
    assert neighbor["comparable_hours"] == 1
    assert neighbor["vs_target"] == "低于"
