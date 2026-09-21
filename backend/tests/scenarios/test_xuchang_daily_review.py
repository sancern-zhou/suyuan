import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_daily_review.episodes import (
    DailyReviewAnalysisState,
    build_anchor,
    episode_intersects_date,
    evidence_version,
    load_episode_anchors,
    resolve_source_evidence,
)
from app.scenarios.xuchang_daily_review.regional_response import (
    REGIONAL_RISE_THRESHOLDS,
    _window_hours,
    calculate_regional_response,
    classify_station_response,
    regional_classification,
    spatial_gradient,
    temporal_lead_lag,
)
import pytest

TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
def _use_file_episode_state(monkeypatch):
    monkeypatch.setenv("XUCHANG_STATION_EPISODE_STORAGE", "file")


def _rows(station_id: str, values: dict[int, float], lat=None, lon=None, **extra):
    return [
        {"station_id": station_id, "name": extra.get("name", station_id), "pm25": value,
         "data_time": datetime(2026, 8, 5, hour), "lat": lat, "lon": lon,
         "station_type": "regular", "district": extra.get("district")}
        for hour, value in values.items()
    ]


def test_window_hours_cover_before_during_after():
    windows = _window_hours("2026-08-05T11:00:00+08:00", "2026-08-05T11:00:00+08:00")
    assert [hour.hour for hour in windows["before"]] == [8, 9, 10]
    assert [hour.hour for hour in windows["during"]] == [11]
    assert [hour.hour for hour in windows["after"]] == [12, 13, 14]


def test_window_hours_span_cross_midnight_episode():
    windows = _window_hours("2026-08-05T23:00:00+08:00", "2026-08-06T01:00:00+08:00")
    assert [hour.hour for hour in windows["during"]] == [23, 0, 1]
    assert [hour.hour for hour in windows["after"]] == [2, 3, 4]
    assert [hour.hour for hour in windows["before"]] == [20, 21, 22]


def test_station_response_rise_flat_decline_and_insufficient():
    windows = _window_hours("2026-08-05T11:00:00+08:00", "2026-08-05T11:00:00+08:00")
    thresholds = REGIONAL_RISE_THRESHOLDS["PM2.5"]
    rise = classify_station_response(
        {"station_id": "A", "station_type": "regular"},
        _series({8: 20, 9: 20, 10: 20, 11: 45, 12: 22, 13: 20, 14: 18}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert rise["during_classification"] == "rise"
    assert rise["during_delta"] == 25.0
    assert rise["after_classification"] == "flat"
    decline = classify_station_response(
        {"station_id": "B", "station_type": "regular"},
        _series({8: 40, 9: 40, 10: 40, 11: 25, 12: 20, 13: 20, 14: 20}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert decline["during_classification"] == "decline"
    flat = classify_station_response(
        {"station_id": "C", "station_type": "regular"},
        _series({8: 20, 9: 20, 10: 20, 11: 25, 12: 20, 13: 20, 14: 20}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert flat["during_classification"] == "flat"
    insufficient = classify_station_response(
        {"station_id": "D", "station_type": "regular"},
        _series({10: 20, 11: 45}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert insufficient["during_classification"] == "insufficient_data"
    assert insufficient["before"]["status"] == "insufficient_data"


def _series(values: dict[int, float]) -> dict[datetime, float]:
    return {datetime(2026, 8, 5, hour): value for hour, value in values.items()}


def test_first_rise_hour_and_lead_status():
    windows = _window_hours("2026-08-05T11:00:00+08:00", "2026-08-05T11:00:00+08:00")
    thresholds = REGIONAL_RISE_THRESHOLDS["PM2.5"]
    early = classify_station_response(
        {"station_id": "A", "station_type": "regular"},
        _series({8: 20, 9: 20, 10: 40, 11: 45, 12: 40, 13: 30, 14: 25}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert early["first_rise_hour"] == "2026-08-05T10:00:00"
    assert early["lead_hours_to_target"] == -1
    assert early["lead_status"] == "lead"
    late = classify_station_response(
        {"station_id": "B", "station_type": "regular"},
        _series({8: 20, 9: 20, 10: 20, 11: 20, 12: 45, 13: 40, 14: 30}),
        windows, datetime(2026, 8, 5, 11), thresholds, is_target=False,
    )
    assert late["lead_hours_to_target"] == 1
    assert late["lead_status"] == "lag"


def test_regional_classification_priority_rules():
    def neighbor(classification):
        return {"station_id": classification, "during_classification": classification,
                "after_classification": classification if classification != "insufficient_data" else "insufficient_data",
                "during_delta": 20.0}

    target = {"during_classification": "rise"}
    co_rise = regional_classification(target, [neighbor("rise")] * 3 + [neighbor("flat"), neighbor("flat")])
    assert co_rise["classification"] == "regional_co_rise"
    local = regional_classification(target, [neighbor("rise"), neighbor("flat"), neighbor("flat"), neighbor("flat")])
    assert local["classification"] == "local_target_only"
    decline = regional_classification(target, [neighbor("decline")] * 3 + [neighbor("flat")])
    assert decline["classification"] == "regional_decline"
    few = regional_classification(target, [neighbor("rise"), neighbor("flat")])
    assert few["classification"] == "insufficient_evidence"


def test_regional_classification_delayed_requires_after_window_gain():
    def station(during, after):
        return {"station_id": during + after, "during_classification": during,
                "after_classification": after, "during_delta": 5.0}

    delayed = regional_classification(
        {"during_classification": "rise"},
        [station("flat", "rise")] * 3 + [station("flat", "flat")] * 2,
    )
    assert delayed["classification"] == "delayed_regional_rise"
    assert delayed["after_rise_ratio"] - delayed["during_rise_ratio"] >= 0.2


def test_temporal_lead_lag_aggregates_statuses():
    neighbors = [
        {"station_id": "A", "station_type": "regular", "lead_status": "lead",
         "lead_hours_to_target": -2, "first_rise_hour": "2026-08-05T09:00:00"},
        {"station_id": "B", "station_type": "township", "lead_status": "lead",
         "lead_hours_to_target": -1, "first_rise_hour": "2026-08-05T10:00:00"},
        {"station_id": "C", "station_type": "township", "lead_status": "synchronous",
         "lead_hours_to_target": 0, "first_rise_hour": "2026-08-05T11:00:00"},
        {"station_id": "D", "station_type": "township", "lead_status": "no_detected_rise",
         "lead_hours_to_target": None, "first_rise_hour": None},
    ]
    result = temporal_lead_lag(neighbors, "2026-08-05T11:00:00+08:00")
    assert result["detected_rise_count"] == 3
    assert result["lead_count"] == 2
    assert result["no_detected_rise_count"] == 1
    assert result["median_lead_hours_to_target"] == -1.0


def test_spatial_missing_coordinates_when_township_only():
    target = {"station_id": "T", "lat": None, "lon": None, "during_delta": 30.0}
    neighbors = [
        {"station_id": "1107B", "station_type": "township", "lat": None, "lon": None,
         "during_delta": 20.0, "coordinate_status": "missing_coordinates"},
    ]
    result = spatial_gradient(target, neighbors)
    assert result["spatial_status"] == "insufficient_coordinates"
    assert result["reason"] == "target_station_coordinates_missing"


def test_spatial_township_neighbors_without_coordinates_are_excluded_from_geometry():
    target = {"station_id": "T", "lat": 34.03, "lon": 113.85, "during_delta": 30.0}
    neighbors = [
        {"station_id": "1107B", "station_type": "township", "lat": None, "lon": None,
         "during_delta": 20.0, "coordinate_status": "missing_coordinates"},
        {"station_id": "XC002", "station_type": "regular", "lat": 34.1, "lon": 113.9,
         "during_delta": 10.0, "coordinate_status": "available"},
    ]
    result = spatial_gradient(target, neighbors)
    assert result["spatial_status"] == "partial_coordinates"
    assert result["neighbor_count_with_coordinates"] == 1
    assert result["neighbor_count_without_coordinates"] == 1
    assert result["plane_fit"]["status"] == "not_run"
    assert "fewer_than_3" in result["plane_fit"]["reason"]
    assert result["coordinate_coverage"]["township"] == "missing_coordinates"


def test_spatial_plane_fit_runs_with_three_non_collinear_stations():
    target = {"station_id": "T", "lat": 34.03, "lon": 113.85, "during_delta": 30.0}
    neighbors = [
        {"station_id": "A", "station_type": "regular", "lat": 34.10, "lon": 113.90,
         "during_delta": 10.0, "coordinate_status": "available"},
        {"station_id": "B", "station_type": "regular", "lat": 34.20, "lon": 113.80,
         "during_delta": 5.0, "coordinate_status": "available"},
        {"station_id": "C", "station_type": "regular", "lat": 34.00, "lon": 113.95,
         "during_delta": 15.0, "coordinate_status": "available"},
    ]
    result = spatial_gradient(target, neighbors)
    assert result["spatial_status"] == "computed"
    fit = result["plane_fit"]
    assert fit["status"] == "ok"
    assert fit["sample_count"] == 3
    assert fit["gradient_magnitude_per_km"] >= 0
    assert 0 <= fit["bearing_deg_toward_increase"] < 360
    assert result["neighbor_geometry"][0]["radial_gradient_per_km"] is not None


def test_episode_selection_intersects_date_only():
    episode = {"started_at": "2026-08-05T23:00:00+08:00", "last_seen_at": "2026-08-06T01:00:00+08:00"}
    assert episode_intersects_date(episode, date(2026, 8, 5))
    assert episode_intersects_date(episode, date(2026, 8, 6))
    assert not episode_intersects_date(episode, date(2026, 8, 7))


def test_evidence_version_changes_on_material_update():
    episode = {"episode_id": "ep-1", "event_ids": ["a"], "hour_count": 1,
               "peak_station_value": 60, "peak_deviation_ratio": 1.0,
               "started_at": "2026-08-05T11:00:00+08:00", "last_seen_at": "2026-08-05T11:00:00+08:00"}
    updated = {**episode, "peak_station_value": 90, "event_ids": ["a", "b"], "hour_count": 2}
    assert evidence_version(episode) != evidence_version(updated)


def test_evidence_version_changes_when_source_features_attach():
    episode = {"episode_id": "ep-1", "event_ids": ["a"], "hour_count": 1,
               "peak_station_value": 60, "peak_deviation_ratio": 1.0,
               "started_at": "2026-08-05T11:00:00+08:00", "last_seen_at": "2026-08-05T11:00:00+08:00"}
    without_features = evidence_version(episode)
    with_features = evidence_version(episode, {
        "status": "found",
        "matched_alerts": [
            {"event_id": "a", "pollutant_source_features": {"status": "calculated"}},
        ],
    })
    assert without_features != with_features
    no_evidence = evidence_version(episode, {"status": "not_found", "matched_alerts": []})
    assert no_evidence != with_features


def test_resolve_source_evidence_matches_event_ids(tmp_path: Path):
    evidence_dir = tmp_path / "20260805"
    evidence_dir.mkdir(parents=True)
    path = evidence_dir / "xuchang-station-episode-202608051100-XC001-abc.evidence.json"
    path.write_text(json.dumps({
        "schema_version": "xuchang_station_deviation_episode_evidence/v1",
        "alerts": [
            {"alert": {"event_id": "ev-11", "occurred_at": "2026-08-05T11:00:00+08:00",
                       "station_value": 60.0, "target_pollutant": "PM2.5"}},
            {"alert": {"event_id": "other", "occurred_at": "2026-08-05T09:00:00+08:00",
                       "station_value": 10.0}},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    episode = {"episode_id": "ep-1", "event_ids": ["ev-11"]}
    result = resolve_source_evidence(tmp_path, episode, date(2026, 8, 5))
    assert result["status"] == "found"
    assert len(result["matched_alerts"]) == 1


def test_resolve_source_evidence_accepts_legacy_inner_schema(tmp_path: Path):
    evidence_dir = tmp_path / "20260805"
    evidence_dir.mkdir(parents=True)
    path = evidence_dir / "xuchang-station-episode-202608051100-XC001-abc.evidence.json"
    path.write_text(json.dumps({
        "schema_version": "xuchang_station_deviation_evidence/v3",
        "alerts": [
            {"alert": {"event_id": "ev-11", "occurred_at": "2026-08-05T11:00:00+08:00",
                       "station_value": 60.0, "target_pollutant": "PM2.5",
                       "pollutant_source_features": {"status": "calculated", "sample_count": 12}}},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    episode = {"episode_id": "ep-1", "event_ids": ["ev-11"]}
    result = resolve_source_evidence(tmp_path, episode, date(2026, 8, 5))
    assert result["status"] == "found"
    assert result["matched_alerts"][0]["pollutant_source_features"]["sample_count"] == 12


def test_build_anchor_uses_alert_hours_and_peak(tmp_path: Path):
    episode = {
        "episode_id": "ep-1", "status": "closed", "station_id": "XC001",
        "station_name": "目标站", "target_pollutant": "PM2.5",
        "measurement_granularity": "hour", "alert_type": "hourly_deviation",
        "started_at": "2026-08-05T10:00:00+08:00", "last_seen_at": "2026-08-05T12:00:00+08:00",
        "event_ids": ["ev-10", "ev-11", "ev-12"], "hour_count": 3,
        "peak_station_value": 80.0, "peak_deviation_ratio": 1.5,
    }
    source = {
        "status": "found",
        "path": "/tmp/evidence.json",
        "matched_alerts": [
            {"event_id": "ev-10", "occurred_at": "2026-08-05T10:00:00+08:00", "station_value": 60.0},
            {"event_id": "ev-11", "occurred_at": "2026-08-05T11:00:00+08:00", "station_value": 80.0},
            {"event_id": "ev-12", "occurred_at": "2026-08-05T12:00:00+08:00", "station_value": 70.0},
        ],
    }
    anchor = build_anchor(episode, date(2026, 8, 5), source)
    assert anchor["episode_start"] == "2026-08-05T10:00:00"
    assert anchor["episode_end"] == "2026-08-05T12:00:00"
    assert anchor["peak_time"] == "2026-08-05T11:00:00+08:00"
    assert anchor["peak_value"] == 80.0
    assert anchor["evidence_version"] == evidence_version(episode, source)
    assert anchor["source_evidence_package_path"] == "/tmp/evidence.json"


def test_build_anchor_extracts_source_features_from_matched_alerts():
    episode = {
        "episode_id": "ep-1", "status": "closed", "station_id": "XC001",
        "target_pollutant": "PM2.5", "started_at": "2026-08-05T10:00:00+08:00",
        "last_seen_at": "2026-08-05T11:00:00+08:00", "event_ids": ["ev-10"],
    }
    features = {"status": "calculated", "sample_count": 12, "classification": "biomass_burning"}
    source = {
        "status": "found",
        "path": "/tmp/evidence.json",
        "matched_alerts": [
            {"event_id": "ev-10", "occurred_at": "2026-08-05T10:00:00+08:00",
             "station_value": 60.0, "pollutant_source_features": features},
        ],
    }
    anchor = build_anchor(episode, date(2026, 8, 5), source)
    assert anchor["source_features"] == [features]
    assert anchor["alert_hours"] == ["2026-08-05T10:00:00"]


def test_build_anchor_keeps_episode_state_boundary_when_evidence_omits_suppressed_alerts():
    episode = {
        "episode_id": "ep-1", "status": "closed", "station_id": "XC001",
        "target_pollutant": "PM2.5", "started_at": "2026-08-05T10:00:00+08:00",
        "last_seen_at": "2026-08-05T12:00:00+08:00", "event_ids": ["ev-10", "ev-11", "ev-12"],
    }
    anchor = build_anchor(
        episode,
        date(2026, 8, 5),
        {"status": "found", "path": "/tmp/evidence.json", "matched_alerts": [
            {"event_id": "ev-10", "occurred_at": "2026-08-05T10:00:00+08:00", "station_value": 60.0},
        ]},
    )
    assert anchor["episode_start"] == "2026-08-05T10:00:00"
    assert anchor["episode_end"] == "2026-08-05T12:00:00"


def test_load_episode_anchors_filters_other_dates(tmp_path: Path):
    state_path = tmp_path / "episode_state.json"
    state_path.write_text(json.dumps({
        "schema_version": "xuchang_station_deviation_episodes/v1",
        "active": {},
        "history": [
            {"episode_id": "ep-in-range", "status": "closed", "station_id": "XC001",
             "target_pollutant": "PM2.5", "started_at": "2026-08-05T11:00:00+08:00",
             "last_seen_at": "2026-08-05T11:00:00+08:00", "event_ids": ["ev-11"]},
            {"episode_id": "ep-other-day", "status": "closed", "station_id": "XC001",
             "target_pollutant": "PM2.5", "started_at": "2026-08-01T11:00:00+08:00",
             "last_seen_at": "2026-08-01T11:00:00+08:00", "event_ids": ["ev-01"]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    result = load_episode_anchors(state_path, date(2026, 8, 5), evidence_root=tmp_path)
    assert result["status"] == "found"
    assert [item["episode_id"] for item in result["episodes"]] == ["ep-in-range"]


def test_load_episode_anchors_prefers_database_episode(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XUCHANG_STATION_EPISODE_STORAGE", "database")
    state_path = tmp_path / "episode_state.json"
    state_path.write_text(json.dumps({"active": {}, "history": []}), encoding="utf-8")
    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.episode_storage_db.query_episodes",
        lambda target_date: [{
            "episode_id": "ep-db", "status": "closed", "station_id": "XC001",
            "target_pollutant": "PM2.5", "started_at": "2026-08-05T11:00:00",
            "last_seen_at": "2026-08-05T12:00:00", "event_ids": ["ev-db"],
        }],
    )
    result = load_episode_anchors(state_path, date(2026, 8, 5), evidence_root=tmp_path)
    assert result["episode_source"] == "database"
    assert [item["episode_id"] for item in result["episodes"]] == ["ep-db"]


def test_analysis_state_dedup_and_version_chain(tmp_path: Path):
    state = DailyReviewAnalysisState(tmp_path / "analysis_state.json")
    first = state.resolve("ep-1", "abc123", "analysis-base")
    assert first["analysis_status"] == "new"
    assert first["analysis_id"] == "analysis-base"
    duplicate = state.resolve("ep-1", "abc123", "analysis-base")
    assert duplicate["analysis_status"] == "duplicate"
    newer = state.resolve("ep-1", "def456", "analysis-base")
    assert newer["analysis_status"] == "new_version"
    assert newer["analysis_id"] == "analysis-base-v2"
    assert newer["parent_analysis_id"] == "analysis-base"


def test_calculate_regional_response_full_flow():
    anchor = {
        "analysis_id": "analysis-1",
        "episode_id": "ep-1",
        "target_date": "2026-08-05",
        "evidence_version": "abc123",
        "parent_alert_event_ids": ["ev-11"],
        "source_evidence_package_path": "/tmp/evidence.json",
        "station_id": "XC001",
        "station_name": "目标站",
        "target_pollutant": "PM2.5",
        "episode_start": "2026-08-05T11:00:00",
        "episode_end": "2026-08-05T11:00:00",
        "alert_hours": ["2026-08-05T11:00:00"],
        "peak_time": "2026-08-05T11:00:00+08:00",
        "peak_value": 60.0,
        "episode_status": "closed",
        "alert_type": "hourly_deviation",
        "measurement_granularity": "hour",
    }
    regular_rows = (
        _rows("XC001", {8: 20, 9: 20, 10: 20, 11: 60, 12: 55, 13: 50, 14: 45}, 34.03, 113.85)
        + _rows("XC002", {8: 20, 9: 20, 10: 40, 11: 50, 12: 45, 13: 40, 14: 35}, 34.10, 113.90)
        + _rows("XC003", {8: 20, 9: 20, 10: 40, 11: 45, 12: 40, 13: 35, 14: 30}, 34.20, 114.00)
    )
    township_rows = [
        {"station_id": "1107B", "name": "长葛市和尚桥镇", "district": "长葛市",
         "data_time": datetime(2026, 8, 5, hour), "pm25": value,
         "station_type": "township", "lat": None, "lon": None}
        for hour, value in {8: 22, 9: 22, 10: 24, 11: 45, 12: 40, 13: 35, 14: 30}.items()
    ] + [
        {"station_id": "1108B", "name": "长葛市南席镇", "district": "长葛市",
         "data_time": datetime(2026, 8, 5, hour), "pm25": value,
         "station_type": "township", "lat": None, "lon": None}
        for hour, value in {8: 20, 9: 20, 10: 20, 11: 25, 12: 22, 13: 20, 14: 20}.items()
    ]
    result = calculate_regional_response(
        anchor, regular_rows=regular_rows, township_rows=township_rows
    )
    assert result["calculation_status"] == "calculated"
    assert result["regional_co_rise"]["classification"] == "regional_co_rise"
    assert result["regional_co_rise"]["during_rise_ratio"] >= 0.6
    assert result["temporal_lead_lag"]["median_lead_hours_to_target"] < 0
    assert result["transport_consistency"]["conclusion"] == "neighbor_lead_rise"
    assert result["transport_consistency"]["conclusion_label"] == "周边提前抬升"
    township_responses = [
        item for item in result["station_response_by_window"]
        if item["station_type"] == "township"
    ]
    assert all(item["coordinate_status"] == "missing_coordinates" for item in township_responses)
    assert result["spatial_gradient"]["coordinate_coverage"]["township"] == "missing_coordinates"
    assert {item["district"] for item in result["township_district_summary"]} == {"长葛市"}
    assert result["window_policy"]["window_minimum_samples"] == {"before": 2, "during": 1, "after": 2}


def test_calculate_regional_response_not_enabled_pollutant():
    anchor = {
        "analysis_id": "analysis-1",
        "episode_id": "ep-2",
        "target_date": "2026-08-05",
        "evidence_version": "abc123",
        "parent_alert_event_ids": [],
        "source_evidence_package_path": None,
        "station_id": "XC001",
        "station_name": "目标站",
        "target_pollutant": "BSP",
        "episode_start": "2026-08-05T11:00:00",
        "episode_end": "2026-08-05T11:00:00",
        "alert_hours": [],
        "peak_time": None,
        "peak_value": None,
        "episode_status": "closed",
    }
    result = calculate_regional_response(anchor, regular_rows=[], township_rows=[])
    assert result["calculation_status"] == "not_enabled_for_pollutant"
    assert "PM2.5" in result["enabled_pollutants"]
    assert {"NO2", "NOX", "PM10", "CO"} <= set(result["enabled_pollutants"])


def test_nox_uses_no2_series_proxy():
    anchor = {
        "analysis_id": "analysis-1",
        "episode_id": "ep-nox",
        "target_date": "2026-08-05",
        "evidence_version": "abc123",
        "parent_alert_event_ids": [],
        "station_id": "XC001",
        "station_name": "目标站",
        "target_pollutant": "NOX",
        "episode_start": "2026-08-05T11:00:00",
        "episode_end": "2026-08-05T11:00:00",
        "alert_hours": ["2026-08-05T11:00:00"],
        "peak_time": "2026-08-05T11:00:00+08:00",
        "peak_value": 60.0,
        "episode_status": "closed",
    }
    rows = []
    for station_id, values in (("XC001", {9: 20, 10: 20, 11: 60, 12: 55}),
                               ("XC002", {9: 20, 10: 20, 11: 58, 12: 50}),
                               ("XC003", {9: 20, 10: 20, 11: 57, 12: 48}),
                               ("XC004", {9: 20, 10: 20, 11: 21, 12: 20})):
        for hour, no2 in values.items():
            rows.append({"station_id": station_id, "name": f"站点{station_id}", "no2": no2,
                         "data_time": datetime(2026, 8, 5, hour)})
    result = calculate_regional_response(anchor, regular_rows=rows, township_rows=[])
    assert result["calculation_status"] == "calculated"
    assert result["series_proxy_note"] == "NOX告警以站点NO2小时浓度为空间异常代理"
    assert result["target_response"]["during"]["mean"] == 60.0
