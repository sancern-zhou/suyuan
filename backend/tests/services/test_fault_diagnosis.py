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


def test_processes_main_pollutant_constant_streak_as_data_quality_fault(tmp_path):
    event_dir = tmp_path / "深圳" / "run1" / "evt1"
    evidence_pack = _write_json(
        event_dir / "evidence_pack.json",
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "深圳",
            "event": {
                "event_id": "evt1",
                "main_pollutant": "PM10",
                "time_range": {"start": "2026-07-01 00:00:00", "end": "2026-07-01 02:00:00"},
            },
            "event_summary": {
                "main_pollutant": "PM10",
                "city_peak": {"value": 35, "timestamp": "2026-07-01 01:00:00"},
                "station_peaks": [
                    {"station_name": "坪山", "peak_value": 45, "timestamp": "2026-07-01 01:00:00", "unit": "ug/m3"},
                    {"station_name": "观澜", "peak_value": 41, "timestamp": "2026-07-01 01:00:00", "unit": "ug/m3"},
                ],
            },
        },
    )
    conclusion = _write_json(
        event_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt1",
            "city": "深圳",
            "main_pollutant": "PM10",
            "classification": "suspected_device_or_data_fault",
            "reason_codes": ["main_pollutant_constant_streak", "multi_station_coherent"],
            "source_evidence_pack": str(evidence_pack),
            "downstream": {
                "requires_fault_diagnosis": True,
                "processed_by_fault_diagnosis": False,
            },
        },
    )

    result = FaultDiagnosisService(output_root=tmp_path).process_conclusion(conclusion)

    cause = result["most_likely_causes"][0]
    assert cause["cause"] == "监测仪或数采链路恒值异常"
    assert cause["cause_type"] == "data_quality"
    assert "同城多站点存在一致变化，削弱单站设备故障判断" in cause["contradicting_evidence"]
    assert result["affected_stations"][0]["station_name"] == "坪山"
    assert result["affected_stations"][0]["peak_value"] == 45
    assert "坪山" in result["summary"]


def test_single_station_dominant_alone_is_labeled_as_pending_review(tmp_path):
    event_dir = tmp_path / "东莞" / "run1" / "evt1"
    evidence_pack = _write_json(
        event_dir / "evidence_pack.json",
        {
            "schema_version": "pollution_event_evidence_pack/v1",
            "city": "东莞",
            "event": {"event_id": "evt1", "main_pollutant": "AQI"},
            "event_summary": {"dominant_station_count": 1},
        },
    )
    conclusion = _write_json(
        event_dir / "event_conclusion.json",
        {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": "evt1",
            "city": "东莞",
            "main_pollutant": "AQI",
            "classification": "suspected_device_or_data_fault",
            "reason_codes": ["single_station_dominant"],
            "source_evidence_pack": str(evidence_pack),
            "downstream": {
                "requires_fault_diagnosis": True,
                "processed_by_fault_diagnosis": False,
            },
        },
    )

    result = FaultDiagnosisService(output_root=tmp_path).process_conclusion(conclusion)

    cause = result["most_likely_causes"][0]
    assert cause["cause"] == "单站局地影响或数据链路异常待复核"
    assert cause["cause_type"] == "needs_review"
    assert cause["confidence"] == "low"
