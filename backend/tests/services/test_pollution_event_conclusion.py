import json
from pathlib import Path

from app.services.pollution_event_conclusion import (
    EventConclusionClassification,
    PollutionEventConclusionService,
)


def _write_pack(tmp_path: Path, payload: dict) -> Path:
    pack = tmp_path / "evidence_pack.json"
    pack.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return pack


def test_classifies_single_station_peer_mismatch_as_suspected_fault(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "广州",
            "event": {
                "event_id": "evt_1",
                "main_pollutant": "PM2_5",
                "time_range": {
                    "start": "2026-07-01 08:00:00",
                    "end": "2026-07-01 10:00:00",
                },
                "triggered_by": ["absolute_threshold"],
            },
            "event_summary": {
                "station_count": 5,
                "dominant_station_count": 1,
                "peer_trend_consistent": False,
            },
            "observed_signal_summary": {
                "dominant_station_names": ["站点A"],
                "pollutant_relationships": {"pm_cochange": "weak"},
            },
            "quality_gate": {"status": "ok"},
            "fetch_errors": [],
            "data_files": {"station_hour_monitoring": "station_hour_monitoring.json"},
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert result.classification == EventConclusionClassification.SUSPECTED_DEVICE_OR_DATA_FAULT
    assert "single_station_dominant" in result.reason_codes
    assert "peer_trend_inconsistent" in result.reason_codes
    saved = json.loads((tmp_path / "event_conclusion.json").read_text(encoding="utf-8"))
    assert saved["downstream"]["requires_fault_diagnosis"] is True


def test_classifies_coherent_multi_station_event_as_normal_pollution(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "深圳",
            "event": {
                "event_id": "evt_2",
                "main_pollutant": "O3_8h",
                "time_range": {
                    "start": "2026-07-01 12:00:00",
                    "end": "2026-07-01 16:00:00",
                },
                "triggered_by": ["absolute_threshold"],
            },
            "event_summary": {
                "station_count": 8,
                "dominant_station_count": 5,
                "peer_trend_consistent": True,
            },
            "observed_signal_summary": {
                "meteorology_supports_accumulation": True,
                "regional_signal": "coherent",
            },
            "quality_gate": {"status": "ok"},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert result.classification == EventConclusionClassification.NORMAL_POLLUTION
    assert result.downstream["requires_fault_diagnosis"] is False


def test_classifies_missing_evidence_as_insufficient(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "佛山",
            "event": {
                "event_id": "evt_3",
                "main_pollutant": "PM10",
                "time_range": {
                    "start": "2026-07-01 08:00:00",
                    "end": "2026-07-01 09:00:00",
                },
            },
            "event_summary": {"station_count": 0},
            "quality_gate": {"status": "limited"},
            "fetch_errors": [{"source": "station_hour", "error": "no records"}],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert result.classification == EventConclusionClassification.INSUFFICIENT_EVIDENCE
    assert "station_hour_missing" in result.reason_codes


def test_no2_o3_pattern_weak_alone_is_insufficient_not_fault(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "东莞",
            "event": {
                "event_id": "evt_o3",
                "main_pollutant": "O3_8h",
                "time_range": {"start": "2026-07-01 13:00:00", "end": "2026-07-01 18:00:00"},
            },
            "event_summary": {
                "station_count": 8,
                "cochange": [{"pollutant": "NO2", "correlation": 0.45, "points": 8}],
            },
            "quality_gate": {"status": "caution"},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert "no2_o3_pattern_weak" in result.reason_codes
    assert result.classification == EventConclusionClassification.INSUFFICIENT_EVIDENCE
    assert result.downstream["requires_fault_diagnosis"] is False


def test_single_station_dominant_alone_does_not_require_fault_diagnosis(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "东莞",
            "event": {
                "event_id": "evt_single_station",
                "main_pollutant": "AQI",
                "time_range": {"start": "2026-07-01 08:00:00", "end": "2026-07-01 10:00:00"},
            },
            "event_summary": {
                "station_count": 6,
                "dominant_station_count": 1,
                "peer_trend_consistent": True,
            },
            "quality_gate": {"status": "ok"},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert "single_station_dominant" in result.reason_codes
    assert result.classification == EventConclusionClassification.INSUFFICIENT_EVIDENCE
    assert result.downstream["requires_fault_diagnosis"] is False


def test_single_station_with_supported_pm_cochange_does_not_require_fault_diagnosis(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "佛山",
            "event": {
                "event_id": "evt_single_pm_supported",
                "main_pollutant": "PM2_5",
                "time_range": {"start": "2026-07-01 08:00:00", "end": "2026-07-01 10:00:00"},
            },
            "event_summary": {
                "station_count": 5,
                "dominant_station_count": 1,
                "cochange": [{"pollutant": "PM10", "correlation": 0.92, "points": 5}],
            },
            "quality_gate": {"status": "ok"},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert "single_station_dominant" in result.reason_codes
    assert "pm_cochange_supported" in result.reason_codes
    assert result.classification == EventConclusionClassification.NORMAL_POLLUTION
    assert result.downstream["requires_fault_diagnosis"] is False


def test_write_conclusion_is_idempotent_and_uses_existing_pack(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "广州",
            "event": {
                "event_id": "evt_4",
                "main_pollutant": "NO2",
                "time_range": {
                    "start": "2026-07-01 08:00:00",
                    "end": "2026-07-01 09:00:00",
                },
            },
            "event_summary": {
                "station_count": 4,
                "dominant_station_count": 1,
                "peer_trend_consistent": False,
            },
            "quality_gate": {"status": "ok"},
            "fetch_errors": [],
        },
    )

    service = PollutionEventConclusionService()
    first = service.write_conclusion(pack)
    second = service.write_conclusion(pack)

    assert first.classification == second.classification
    payload = json.loads((tmp_path / "event_conclusion.json").read_text(encoding="utf-8"))
    assert payload["event_id"] == "evt_4"


def test_classifies_real_pack_shape_with_pm_cochange_as_normal_pollution(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "广州",
            "event": {
                "event_id": "evt_real_1",
                "main_pollutant": "PM2_5",
                "time_range": {"start": "2026-07-01 08:00:00", "end": "2026-07-01 10:00:00"},
            },
            "event_summary": {
                "main_pollutant": "PM2_5",
                "station_peaks": [
                    {"station_name": "A", "peak_value": 27},
                    {"station_name": "B", "peak_value": 25},
                    {"station_name": "C", "peak_value": 24},
                    {"station_name": "D", "peak_value": 23},
                ],
                "cochange": [{"pollutant": "PM10", "correlation": 0.91, "points": 4}],
                "record_counts": {"city_hour": 4, "station_hour": 120, "weather_hour": 100},
            },
            "observed_signal_summary": {},
            "quality_gate": {"status": "caution", "high_issue_count": 0, "interpretation_limits": []},
            "data_quality": {"issues": []},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert result.classification == EventConclusionClassification.NORMAL_POLLUTION
    assert "pm_cochange_supported" in result.reason_codes


def test_classifies_real_pack_shape_main_pollutant_constant_as_suspected_fault(tmp_path):
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "深圳",
            "event": {
                "event_id": "evt_real_2",
                "main_pollutant": "PM10",
                "time_range": {"start": "2026-07-01 00:00:00", "end": "2026-07-01 04:00:00"},
            },
            "event_summary": {
                "main_pollutant": "PM10",
                "station_peaks": [
                    {"station_name": "A", "peak_value": 35},
                    {"station_name": "B", "peak_value": 20},
                    {"station_name": "C", "peak_value": 18},
                ],
                "cochange": [{"pollutant": "PM2_5", "correlation": 0.89, "points": 8}],
                "record_counts": {"city_hour": 8, "station_hour": 142, "weather_hour": 32},
            },
            "quality_gate": {
                "status": "caution",
                "high_issue_count": 0,
                "interpretation_limits": [
                    {
                        "severity": "medium",
                        "issue_type": "long_constant_value",
                        "pollutant": "PM10",
                        "message": "PM10 has a constant streak of 8 records.",
                    }
                ],
            },
            "data_quality": {"issues": []},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert result.classification == EventConclusionClassification.SUSPECTED_DEVICE_OR_DATA_FAULT
    assert "main_pollutant_constant_streak" in result.reason_codes


def test_ignores_main_pollutant_constant_streak_outside_event_window(tmp_path):
    city_dir = tmp_path / "city"
    city_dir.mkdir()
    city_hour = _write_pack(
        city_dir,
        {
            "records": [
                {"timestamp": "2026-07-01 00:00:00", "measurements": {"PM10": 9}},
                {"timestamp": "2026-07-01 01:00:00", "measurements": {"PM10": 9}},
                {"timestamp": "2026-07-01 02:00:00", "measurements": {"PM10": 9}},
                {"timestamp": "2026-07-01 10:00:00", "measurements": {"PM10": 15}},
                {"timestamp": "2026-07-01 11:00:00", "measurements": {"PM10": 18}},
            ]
        },
    )
    pack = _write_pack(
        tmp_path,
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "深圳",
            "event": {
                "event_id": "evt_real_3",
                "main_pollutant": "PM10",
                "time_range": {"start": "2026-07-01 10:00:00", "end": "2026-07-01 11:00:00"},
            },
            "event_summary": {
                "main_pollutant": "PM10",
                "cochange": [{"pollutant": "PM2_5", "correlation": 0.86, "points": 5}],
                "record_counts": {"city_hour": 5, "station_hour": 20},
            },
            "quality_gate": {
                "status": "caution",
                "high_issue_count": 0,
                "interpretation_limits": [
                    {
                        "severity": "medium",
                        "issue_type": "long_constant_value",
                        "pollutant": "PM10",
                        "message": "PM10 has a constant streak of 3 records.",
                    }
                ],
            },
            "data_files": {"city_hour_monitoring": str(city_hour)},
            "fetch_errors": [],
        },
    )

    result = PollutionEventConclusionService().write_conclusion(pack)

    assert "main_pollutant_constant_streak" not in result.reason_codes
    assert result.classification == EventConclusionClassification.NORMAL_POLLUTION
    assert result.downstream["requires_fault_diagnosis"] is False
