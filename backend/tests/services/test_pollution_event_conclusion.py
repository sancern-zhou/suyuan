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
