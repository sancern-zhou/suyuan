import json
import hashlib
from pathlib import Path

from app.services.fault_diagnosis import FaultDiagnosisService


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_discovers_only_unprocessed_suspicious_conclusions(tmp_path):
    suspicious_dir = tmp_path / "广州" / "run1" / "evt1"
    normal_dir = tmp_path / "广州" / "run1" / "evt2"
    processed_dir = tmp_path / "广州" / "run1" / "evt3"
    _write_json(
        suspicious_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt1",
            "classification": "suspected_device_or_data_fault",
            "source_evidence_pack": str(suspicious_dir / "evidence_pack.json"),
            "downstream": {
                "requires_fault_diagnosis": True,
                "processed_by_fault_diagnosis": False,
            },
        },
    )
    _write_json(suspicious_dir / "evidence_pack.json", {"city": "广州", "event": {"event_id": "evt1"}})
    _write_json(
        normal_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt2",
            "classification": "normal_pollution",
            "downstream": {"requires_fault_diagnosis": False},
        },
    )
    processed_conclusion = _write_json(
        processed_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt3",
            "classification": "suspected_device_or_data_fault",
            "source_evidence_pack": str(processed_dir / "evidence_pack.json"),
            "downstream": {
                "requires_fault_diagnosis": True,
                "processed_by_fault_diagnosis": False,
            },
        },
    )
    _write_json(processed_dir / "evidence_pack.json", {"city": "广州", "event": {"event_id": "evt3"}})
    _write_json(
        processed_dir / "fault_diagnosis" / "diagnosis_manifest.json",
        {
            "source_event_conclusion": str(processed_dir / "event_conclusion.json"),
            "source_checksum": hashlib.sha256(processed_conclusion.read_bytes()).hexdigest(),
        },
    )

    items = FaultDiagnosisService(output_root=tmp_path).discover_pending()

    assert [item.event_id for item in items] == ["evt1"]


def test_processes_suspicious_conclusion_and_writes_fault_outputs(tmp_path):
    event_dir = tmp_path / "广州" / "run1" / "evt1"
    evidence_pack = _write_json(
        event_dir / "evidence_pack.json",
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "广州",
            "event": {
                "event_id": "evt1",
                "main_pollutant": "PM2_5",
                "time_range": {
                    "start": "2026-07-01 08:00:00",
                    "end": "2026-07-01 10:00:00",
                },
            },
            "event_summary": {
                "station_count": 5,
                "dominant_station_count": 1,
                "peer_trend_consistent": False,
            },
            "observed_signal_summary": {"pollutant_relationships": {"pm_cochange": "weak"}},
            "fetch_errors": [],
        },
    )
    conclusion = _write_json(
        event_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt1",
            "city": "广州",
            "main_pollutant": "PM2_5",
            "time_range": {
                "start": "2026-07-01 08:00:00",
                "end": "2026-07-01 10:00:00",
            },
            "classification": "suspected_device_or_data_fault",
            "reason_codes": [
                "single_station_dominant",
                "peer_trend_inconsistent",
                "pm_cochange_weak",
            ],
            "source_evidence_pack": str(evidence_pack),
            "downstream": {
                "requires_fault_diagnosis": True,
                "processed_by_fault_diagnosis": False,
            },
        },
    )

    result = FaultDiagnosisService(output_root=tmp_path).process_conclusion(conclusion)

    assert result["diagnosis_status"] == "completed"
    assert result["most_likely_causes"][0]["cause"] == "采样系统或颗粒物监测链路异常"
    output = event_dir / "fault_diagnosis" / "fault_diagnosis.json"
    assert output.exists()
    manifest = json.loads(
        (event_dir / "fault_diagnosis" / "diagnosis_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["event_id"] == "evt1"
    saved_conclusion = json.loads(conclusion.read_text(encoding="utf-8"))
    assert saved_conclusion["downstream"]["processed_by_fault_diagnosis"] is True
    assert FaultDiagnosisService(output_root=tmp_path).discover_pending() == []
