from datetime import datetime

from app.services.jiangsu_operations_reports import (
    build_backup_quarterly_report,
    build_fault_monthly_report,
)


def test_fault_report_excludes_recurrent_outage_cluster_but_keeps_it_visible():
    rows = [
        {"station_code": "A", "fault_category": "站点断电", "created_at": f"2026-05-{day:02d}T08:00:00", "completed_at": f"2026-05-{day:02d}T12:00:00"}
        for day in (1, 2, 3)
    ] + [{"station_code": "B", "fault_category": "仪器断数", "created_at": "2026-05-04T08:00:00", "completed_at": "2026-05-05T08:00:00"}]
    result = build_fault_monthly_report(rows)
    assert result["input_count"] == 4
    assert result["excluded_recurrent_outage_count"] == 3
    assert result["analyzed_count"] == 1
    assert result["top_stations"] == [{"station": "B", "count": 1}]


def test_backup_report_applies_48_hour_and_30_day_rules_with_deferment_exception():
    result = build_backup_quarterly_report([
        {"station_code": "A", "fault_time": "2026-01-01T00:00:00", "backup_on_time": "2026-01-04T00:00:00", "backup_off_time": "2026-01-10T00:00:00"},
        {"station_code": "B", "backup_on_time": "2026-01-01T00:00:00", "has_deferment": True},
        {"station_code": "C", "backup_on_time": "2026-01-01T00:00:00"},
    ], as_of=datetime(2026, 2, 5))
    assert [item["station"] for item in result["activation_over_48h"]] == ["A"]
    assert [item["station"] for item in result["over_30_days"]] == ["C"]
    assert result["station_frequency"][0] == {"station": "A", "count": 1}


def test_backup_report_uses_asset_ledger_as_inference_and_marks_unknown_identity():
    result = build_backup_quarterly_report([
        {
            "stationCode": "LEDGER-A", "fault_time": "2026-01-01T00:00:00",
            "useDate": "2026-01-02T00:00:00", "stopDate": "2026-01-20T00:00:00",
            "originalMachine": 0,
        },
        {"stationCode": "LEDGER-B", "useDate": "2026-01-01T00:00:00"},
    ], as_of=datetime(2026, 2, 5))
    inferred = result["records"][0]
    assert inferred["evidence_source"] == "ledger_inferred"
    assert inferred["identity_source"] == "inferred_from_asset_flags"
    assert inferred["analyzable"] is True
    assert result["records"][1]["analyzable"] is False
    assert result["evidence_counts"] == {"ledger_inferred": 2}
