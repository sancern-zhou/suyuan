from datetime import date, datetime, timedelta

import pytest

from app.scenarios.xuchang_daily_review.hourly_rise import (
    SERIES_FIELDS,
    attach_minute_clues,
    detect_hourly_rises,
)


DAY = date(2026, 9, 25)


def _rows(pollutant, values, *, start=datetime(2026, 9, 25, 8), station_id="A"):
    field = SERIES_FIELDS[pollutant]
    return [
        {"station_id": station_id, "name": "甲站", "data_time": start + timedelta(hours=index), field: value}
        for index, value in enumerate(values)
    ]


@pytest.mark.parametrize("pollutant,values,minimum", [
    ("PM2.5", [20, 25, 30], 10),
    ("PM10", [30, 37, 45], 15),
    ("NO2", [16, 20, 24], 8),
    ("SO2", [12, 15, 18], 6),
    ("CO", [0.6, 0.75, 0.9], 0.3),
])
def test_inclusive_relative_and_absolute_thresholds(pollutant, values, minimum):
    result = detect_hourly_rises(_rows(pollutant, values), DAY)
    assert result["event_count"] == 1
    event = result["events"][0]
    assert event["duration_hours"] == 2
    assert event["minimum_absolute_rise"] == minimum
    assert event["rise_percent"] == 50
    assert event["rise_absolute"] == minimum
    assert len(event["hourly_observations"]) == 3


@pytest.mark.parametrize("values", [
    [5, 8, 12],      # relative rise alone is insufficient
    [20, 20, 31],    # a single final-hour jump is not sustained
    [20, None, 31],  # no interpolation across missing observations
    [20, 35, 30, 40],  # no recovery after a decline inside a window
    [0, 10, 20],    # zero baseline cannot define a relative rise
])
def test_rejects_nonqualifying_pm10_windows(values):
    assert detect_hourly_rises(_rows("PM10", values), DAY)["event_count"] == 0


def test_overlapping_windows_become_one_process_and_decline_splits():
    rows = _rows("PM2.5", [20, 25, 32, 42, 20, 25, 35])
    result = detect_hourly_rises(rows, DAY)
    assert result["event_count"] == 2
    first, second = result["events"]
    assert first["duration_hours"] == 3
    assert len(first["qualified_windows"]) >= 2
    assert first["end_concentration"] == 42
    assert second["rise_reference_time"] == "2026-09-25T12:00:00"


def test_cross_day_window_uses_previous_evening_as_reference():
    rows = _rows("PM2.5", [20, 25, 30], start=datetime(2026, 9, 24, 22))
    event = detect_hourly_rises(rows, DAY)["events"][0]
    assert event["rise_reference_time"] == "2026-09-24T22:00:00"
    assert event["episode_start"] == "2026-09-24T23:00:00"
    assert event["episode_end"] == "2026-09-25T00:00:00"


def test_conflicting_duplicate_hour_is_not_silently_chosen():
    rows = _rows("PM2.5", [20, 25, 30])
    rows.append({**rows[1], "pm25": 26})
    result = detect_hourly_rises(rows, DAY)
    assert result["duplicate_conflicts"] == 1
    assert result["event_count"] == 0


def test_only_matching_minute_alerts_attach_to_hourly_process():
    event = detect_hourly_rises(_rows("PM10", [30, 37, 45]), DAY)["events"][0]
    anchors = [
        {"episode_id": "minute-in", "station_id": "A", "target_pollutant": "PM10",
         "measurement_granularity": "5min", "alert_type": "station_deviation",
         "source_started_at": "2026-09-25T09:35:00+08:00",
         "source_last_seen_at": "2026-09-25T09:35:00+08:00",
         "source_alerts": [{"event_id": "ev-in", "occurred_at": "2026-09-25T09:35:00+08:00",
                            "source_features": {"classification": "traffic"}}],
         "source_evidence_status": "found"},
        {"episode_id": "minute-out", "station_id": "A", "target_pollutant": "PM10",
         "measurement_granularity": "5min", "source_started_at": "2026-09-25T11:00:00+08:00",
         "source_last_seen_at": "2026-09-25T11:00:00+08:00"},
        {"episode_id": "other-pollutant", "station_id": "A", "target_pollutant": "NO2",
         "measurement_granularity": "5min", "source_started_at": "2026-09-25T09:30:00+08:00"},
        {"episode_id": "hourly-source", "station_id": "A", "target_pollutant": "PM10",
         "measurement_granularity": "hour", "source_started_at": "2026-09-25T09:30:00+08:00"},
    ]
    attach_minute_clues([event], anchors)
    assert event["source_episode_ids"] == ["minute-in"]
    assert event["parent_alert_event_ids"] == ["ev-in"]
    assert event["source_features"] == [{"classification": "traffic"}]
    assert event["minute_clues"][0]["association_method"] == "matched_alert_time"


def test_episode_boundary_without_event_evidence_is_labeled():
    event = detect_hourly_rises(_rows("PM10", [30, 37, 45]), DAY)["events"][0]
    attach_minute_clues([event], [{
        "episode_id": "minute-boundary", "station_id": "A", "target_pollutant": "PM10",
        "measurement_granularity": "5min", "source_started_at": "2026-09-25T09:40:00+08:00",
        "source_last_seen_at": "2026-09-25T09:40:00+08:00", "source_evidence_status": "not_found",
    }])
    assert event["source_episode_ids"] == ["minute-boundary"]
    assert event["minute_clues"][0]["association_method"] == "episode_boundary_time"
    assert event["minute_clues"][0]["event_ids"] == []
