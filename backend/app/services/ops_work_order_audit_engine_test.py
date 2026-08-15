import logging
from datetime import datetime

from app.services import ops_work_order_audit_engine
from app.services.ops_work_order_audit_engine import (
    _fetch_device_history,
    _history_form_seeds,
    _select_rf_forms_with_filter_stats,
    audit_dataset,
    check_rf_forms,
)


def test_select_rf_forms_with_filter_stats_keeps_draft_and_audited_versions(caplog):
    forms = [
        {
            "RF_W_PMCHECKID": "FORM-1",
            "WORKINGORDERCODE": "WO-1",
            "AUDITORUSERID": "",
            "VALUE": "draft",
        },
        {
            "RF_W_PMCHECKID": "FORM-1",
            "WORKINGORDERCODE": "WO-1",
            "AUDITORUSERID": "auditor-1",
            "VALUE": "audited",
        },
    ]

    with caplog.at_level(logging.INFO, logger="app.services.ops_work_order_audit_engine"):
        selected, stats = _select_rf_forms_with_filter_stats("RF_W_PMCHECK", forms)

    assert selected == forms
    assert stats == {
        "raw_count": 2,
        "selected_count": 2,
        "filtered_count": 0,
        "query_error": None,
    }
    assert any(
        "ops_audit_rf_form_filter_stats table=RF_W_PMCHECK raw_count=2 selected_count=2 filtered_count=0"
        in record.message
        and record.table == "RF_W_PMCHECK"
        and record.raw_count == 2
        and record.selected_count == 2
        and record.filtered_count == 0
        for record in caplog.records
    )


def test_check_rf_forms_does_not_emit_rf_missing_for_check_order_without_forms():
    issues = []

    check_rf_forms(
        {"WORKINGORDERCODE": "WO-NO-RF", "DDWORKINGORDERTYPE": "Check"},
        [],
        issues,
        rf_attachment_typecodes=[],
    )

    assert [issue.rule_id for issue in issues] == []


def test_audit_dataset_skips_flow_visual_tasks_when_disabled(monkeypatch):
    calls = {"build": 0, "run": 0}

    def fake_build_flow_visual_tasks(*args, **kwargs):
        calls["build"] += 1
        return [{"working_order_code": "WO-VISUAL"}]

    def fake_run_flow_visual_tasks(*args, **kwargs):
        calls["run"] += 1

    monkeypatch.setattr(ops_work_order_audit_engine, "build_flow_visual_tasks", fake_build_flow_visual_tasks)
    monkeypatch.setattr(ops_work_order_audit_engine, "_run_flow_visual_tasks", fake_run_flow_visual_tasks)

    audit_dataset({"orders": [{"WORKINGORDERCODE": "WO-VISUAL"}]}, enable_visual=False)

    assert calls == {"build": 0, "run": 0}


def test_audit_dataset_runs_flow_visual_tasks_by_default(monkeypatch):
    calls = {"build": 0, "run": 0}

    def fake_build_flow_visual_tasks(*args, **kwargs):
        calls["build"] += 1
        return [{"working_order_code": "WO-VISUAL"}]

    def fake_run_flow_visual_tasks(tasks, record_issues_by_code):
        calls["run"] += 1
        assert tasks == [{"working_order_code": "WO-VISUAL"}]

    monkeypatch.setattr(ops_work_order_audit_engine, "build_flow_visual_tasks", fake_build_flow_visual_tasks)
    monkeypatch.setattr(ops_work_order_audit_engine, "_run_flow_visual_tasks", fake_run_flow_visual_tasks)

    audit_dataset({"orders": [{"WORKINGORDERCODE": "WO-VISUAL"}]})

    assert calls == {"build": 1, "run": 1}


def test_history_form_seeds_use_target_form_device_identity_and_earliest_time(monkeypatch):
    orders = [
        {
            "WORKINGORDERCODE": "WO-NEW",
            "STATIONID": "S-1",
            "DEVICEID": "00000000-0000-0000-0000-000000000000",
            "CREATETIME": "2026-08-07 10:00:00",
        },
        {
            "WORKINGORDERCODE": "WO-OLD",
            "STATIONID": "S-1",
            "CREATETIME": "2026-08-03 10:00:00",
        },
        {
            "WORKINGORDERCODE": "WO-UNRELATED",
            "STATIONID": "S-1",
            "DEVICEID": "DEVICE-IGNORED",
            "CREATETIME": "2026-08-01 10:00:00",
        },
    ]
    rf_forms = {
        "RF_HY_O3VALUEPASS": [
            {"WORKINGORDERCODE": "WO-NEW", "DEVICECODE": " dev-001 "},
            {"WORKINGORDERCODE": "WO-OLD", "DEVICECODE": "DEV-001"},
        ],
        "RF_W_PMCHECK": [
            {"WORKINGORDERCODE": "WO-UNRELATED", "DEVICECODE": "DEV-IGNORED"},
        ],
    }
    monkeypatch.setattr(
        ops_work_order_audit_engine,
        "DEVICE_IDENTITY_PROFILE",
        {"history_match_fields": {"RF_HY_O3VALUEPASS": ["DEVICECODE"]}},
    )

    seeds = _history_form_seeds(
        orders,
        rf_forms,
        ["RF_HY_O3VALUEPASS"],
    )

    assert seeds == [
        {
            "table": "RF_HY_O3VALUEPASS",
            "station_id": "S-1",
            "device_key": "DEV-001",
            "match_field": "DEVICECODE",
            "cutoff": datetime(2026, 8, 3, 10, 0, 0),
        }
    ]


def test_fetch_device_history_queries_only_same_device_recent_target_forms(monkeypatch):
    calls = []

    class Connection:
        def __init__(self):
            self.rollback_count = 0

        def rollback(self):
            self.rollback_count += 1

    class Cursor:
        def __init__(self):
            self.connection = Connection()

    cursor = Cursor()

    def fake_rows(_cursor, sql, params=None):
        calls.append((sql, list(params or [])))
        if "ranked_history" in sql:
            return [
                {
                    "WORKINGORDERCODE": "WO-HISTORY",
                    "DEVICECODE": "DEV-001",
                    "HISTORY_WO_WORKINGORDERID": "HISTORY-ID",
                    "HISTORY_WO_STATIONID": "S-1",
                    "HISTORY_WO_DEVICEID": None,
                    "HISTORY_WO_WORKINGORDERCODE": "WO-HISTORY",
                    "HISTORY_WO_CREATETIME": "2026-07-31 10:00:00",
                    "HISTORY_WO_UPDATETIME": None,
                    "HISTORY_WO_DDORDERCREATETYPE": None,
                    "HISTORY_WO_DDWORKINGORDERTYPE": "Check",
                    "HISTORY_WO_DDURGENCYTYPE": None,
                    "HISTORY_WO_DDWORKINGORDERSTATUS": "Finish",
                    "HISTORY_WO_DDISSUEDTYPE": None,
                    "HISTORY_WO_ORDERTITLE": None,
                    "HISTORY_WO_ORDERCONTENT": None,
                    "HISTORY_WO_CURRENTWORKFLOWSTATUS": None,
                    "HISTORY_WO_CURRENTWORKFLOWPOINT": None,
                    "HISTORY_WO_FINISHTIME": None,
                    "HISTORY_WO_PLANFINISHTIME": None,
                    "HISTORY_WO_MAINTENANCETYPE": None,
                    "HISTORY_WO_TOTALOVERTIME": None,
                    "HISTORY_WO_TOTALEXPENSE": None,
                    "HISTORY_RANK": 1,
                }
            ]
        raise AssertionError(f"unexpected history query: {sql}")

    monkeypatch.setattr(ops_work_order_audit_engine, "rows", fake_rows)
    monkeypatch.setattr(
        ops_work_order_audit_engine,
        "DEVICE_IDENTITY_PROFILE",
        {
            "history_rf_tables": ["RF_HY_O3VALUEPASS"],
            "history_match_fields": {"RF_HY_O3VALUEPASS": ["DEVICECODE"]},
            "recent_per_device_limit": 2,
        },
    )

    result = _fetch_device_history(
        cursor,
        [
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "STATIONID": "S-1",
                "CREATETIME": "2026-08-01 10:00:00",
            }
        ],
        {
            "RF_HY_O3VALUEPASS": [
                {"WORKINGORDERCODE": "WO-CURRENT", "DEVICECODE": "DEV-001"}
            ],
            "RF_W_PMCHECK": [
                {"WORKINGORDERCODE": "WO-CURRENT", "DEVICECODE": "DEV-002"}
            ],
        },
        limit=50,
    )

    assert len(calls) == 1
    history_sql, history_params = calls[0]
    assert "PARTITION BY seed.STATIONID, seed.DEVICE_KEY" in history_sql
    assert "HISTORY_RANK <= 2" in history_sql
    assert "FROM dbo.RF_HY_O3VALUEPASS rf" in history_sql
    assert "rf.DEVICECODE" in history_sql
    assert "RF_W_PMCHECK" not in history_sql
    assert history_params == ["S-1", "DEV-001", "2026-08-01 10:00:00"]
    assert result["orders"][0]["WORKINGORDERCODE"] == "WO-HISTORY"
    assert list(result["rf_forms"]) == ["RF_HY_O3VALUEPASS"]
    assert result["query_info"] == {
        "strategy": "previous_same_form_device",
        "history_rf_tables": ["RF_HY_O3VALUEPASS"],
        "recent_per_device_limit": 2,
        "history_limit": 50,
        "seed_identity_count": 1,
        "query_batch_count": 1,
        "order_count": 1,
    }
    assert cursor.connection.rollback_count == 0


def test_fetch_device_history_skips_database_when_target_form_has_no_device_identity(monkeypatch):
    def unexpected_rows(*_args, **_kwargs):
        raise AssertionError("history database must not be queried without a device identity")

    monkeypatch.setattr(ops_work_order_audit_engine, "rows", unexpected_rows)
    monkeypatch.setattr(
        ops_work_order_audit_engine,
        "DEVICE_IDENTITY_PROFILE",
        {
            "history_rf_tables": ["RF_HY_O3VALUEPASS"],
            "history_match_fields": {"RF_HY_O3VALUEPASS": ["DEVICECODE"]},
        },
    )

    result = _fetch_device_history(
        type("Cursor", (), {})(),
        [{"WORKINGORDERCODE": "WO-1", "STATIONID": "S-1", "CREATETIME": "2026-08-01"}],
        {"RF_HY_O3VALUEPASS": [{"WORKINGORDERCODE": "WO-1"}]},
    )

    assert result["orders"] == []
    assert result["rf_forms"] == {}
    assert result["query_info"]["reason"] == "missing_device_identity"
