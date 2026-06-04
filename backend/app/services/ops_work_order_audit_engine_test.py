import logging

from app.services.ops_work_order_audit_engine import _select_rf_forms_with_filter_stats


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
