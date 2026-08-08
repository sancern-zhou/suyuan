import logging

from app.services import ops_work_order_audit_engine
from app.services.ops_work_order_audit_engine import _select_rf_forms_with_filter_stats, audit_dataset, check_rf_forms


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
