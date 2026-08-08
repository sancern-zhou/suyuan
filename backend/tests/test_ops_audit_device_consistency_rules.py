import json

from app.services.ops_audit.rules.device_consistency_rules import (
    check_device_identity_consistency,
    merge_device_history,
)
from app.services.ops_work_order_audit import inspect_ops_audit, run_ops_audit_rules


def _order(code: str, *, create_time: str = "2026-05-20 10:00:00") -> dict:
    return {
        "WORKINGORDERCODE": code,
        "STATIONID": "ST-1",
        "DEVICEID": "DEV-1",
        "CREATETIME": create_time,
        "FINISHTIME": "2026-05-20 11:00:00",
        "DDWORKINGORDERTYPE": "Check",
        "DDWORKINGORDERSTATUS": "Finish",
        "CURRENTWORKFLOWSTATUS": "Finish",
        "MAINTENANCETYPE": "Week",
        "ORDERCONTENT": "weekly check",
    }


def _form(
    code: str,
    *,
    brand: str = "API",
    model: str = "T100",
    device_code: str = "CO-001",
    remark: str = "正常",
) -> dict:
    return {
        "WORKINGORDERCODE": code,
        "DEVICEBRAND": brand,
        "DEVICEMODEL": model,
        "DEVICECODE": device_code,
        "POLLUTANTTYPE": "CO",
        "REMARK": remark,
    }


def _forms_by_code(current_form: dict, history_form: dict) -> dict:
    return {
        str(current_form["WORKINGORDERCODE"]): [("RF_W_GASEOUSCHECK_CO", current_form)],
        str(history_form["WORKINGORDERCODE"]): [("RF_W_GASEOUSCHECK_CO", history_form)],
    }


def test_device_identity_detects_cross_order_model_mismatch():
    current = _order("WO-CURRENT")
    history = _order("WO-HISTORY", create_time="2026-05-01 10:00:00")
    forms_by_code = _forms_by_code(_form("WO-CURRENT", model="T100"), _form("WO-HISTORY", model="T200"))
    issues = []

    check_device_identity_consistency(
        current,
        forms_by_code["WO-CURRENT"],
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_DEVICE_IDENTITY_INCONSISTENT"
    assert issues[0].field == "device_identity.model"
    evidence = json.loads(issues[0].evidence)
    assert evidence["rf_table"] == "RF_W_GASEOUSCHECK_CO"
    assert evidence["current_table"] == "RF_W_GASEOUSCHECK_CO"
    assert "device_id|ST-1|DEV-1" in evidence["device_match_keys"]
    assert evidence["comparisons"][0]["compare_order_code"] == "WO-HISTORY"
    assert evidence["comparisons"][0]["current_table"] == "RF_W_GASEOUSCHECK_CO"


def test_device_identity_compares_previous_same_table_station_record_without_same_device_id():
    current = _order("WO-CURRENT", create_time="2026-05-20 10:00:00")
    current["DEVICEID"] = "DEV-CURRENT"
    history = _order("WO-HISTORY", create_time="2026-05-01 10:00:00")
    history["DEVICEID"] = "DEV-HISTORY"
    current_form = _form("WO-CURRENT", model="T100", device_code="CO-CURRENT")
    current_form["STATIONID"] = "ST-1"
    current_form["CHECKTIME"] = "2026-05-20 09:00:00"
    history_form = _form("WO-HISTORY", model="T200", device_code="CO-HISTORY")
    history_form["STATIONID"] = "ST-1"
    history_form["CHECKTIME"] = "2026-05-01 09:00:00"
    forms_by_code = _forms_by_code(current_form, history_form)
    issues = []

    check_device_identity_consistency(
        current,
        forms_by_code["WO-CURRENT"],
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert any(issue.rule_id == "RF_DEVICE_IDENTITY_INCONSISTENT" for issue in issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["comparisons"][0]["compare_order_code"] == "WO-HISTORY"
    assert evidence["comparisons"][0]["shared_match_keys"] == ["table_station|RF_W_GASEOUSCHECK_CO|ST-1"]


def test_device_identity_compares_range_fields_with_previous_same_table_station_record():
    current = _order("WO-CURRENT", create_time="2026-05-20 10:00:00")
    history = _order("WO-HISTORY", create_time="2026-05-01 10:00:00")
    current_form = _form("WO-CURRENT")
    current_form["STATIONID"] = "ST-1"
    current_form["CHECKTIME"] = "2026-05-20 09:00:00"
    current_form["RANGEVALUE"] = "0-50 ppm"
    history_form = _form("WO-HISTORY")
    history_form["STATIONID"] = "ST-1"
    history_form["CHECKTIME"] = "2026-05-01 09:00:00"
    history_form["RANGEVALUE"] = "0-100 ppm"
    forms_by_code = _forms_by_code(current_form, history_form)
    issues = []

    check_device_identity_consistency(
        current,
        forms_by_code["WO-CURRENT"],
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert len(issues) == 1
    assert issues[0].field == "device_identity.range"
    evidence = json.loads(issues[0].evidence)
    assert evidence["field"] == "range"
    assert evidence["current_value"] == "0-50 ppm"
    assert evidence["comparisons"][0]["compare_raw"] == "0-100 ppm"


def test_device_identity_matches_pmcheck_history_by_pollutant_type():
    current = _order("WO-CURRENT", create_time="2026-05-20 10:00:00")
    history = _order("WO-HISTORY", create_time="2026-05-13 10:00:00")
    current_forms = [
        (
            "RF_W_PMCHECK",
            _form("WO-CURRENT", model="FH62C14", device_code="PM10-001")
            | {"POLLUTANTTYPE": "PM10", "CHECKTIME": "2026-05-20 09:00:00"},
        ),
        (
            "RF_W_PMCHECK",
            _form("WO-CURRENT", model="SHARP5030", device_code="PM25-001")
            | {"POLLUTANTTYPE": "PM2.5", "CHECKTIME": "2026-05-20 09:00:00"},
        ),
    ]
    history_forms = [
        (
            "RF_W_PMCHECK",
            _form("WO-HISTORY", model="SHARP5030", device_code="PM25-001")
            | {"POLLUTANTTYPE": "PM2.5", "CHECKTIME": "2026-05-13 09:00:00"},
        ),
        (
            "RF_W_PMCHECK",
            _form("WO-HISTORY", model="FH62C14", device_code="PM10-001")
            | {"POLLUTANTTYPE": "PM10", "CHECKTIME": "2026-05-13 09:00:00"},
        ),
    ]
    forms_by_code = {
        "WO-CURRENT": current_forms,
        "WO-HISTORY": history_forms,
    }
    issues = []

    check_device_identity_consistency(
        current,
        current_forms,
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert issues == []


def test_device_identity_no_issue_for_same_identity():
    current = _order("WO-CURRENT")
    history = _order("WO-HISTORY", create_time="2026-05-01 10:00:00")
    forms_by_code = _forms_by_code(_form("WO-CURRENT"), _form("WO-HISTORY"))
    issues = []

    check_device_identity_consistency(
        current,
        forms_by_code["WO-CURRENT"],
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert issues == []


def test_device_identity_replacement_evidence_exempts_current_order():
    current = _order("WO-CURRENT")
    history = _order("WO-HISTORY", create_time="2026-05-01 10:00:00")
    current_forms = [
        ("RF_W_GASEOUSCHECK_CO", _form("WO-CURRENT", model="T100")),
        ("RF_Y_DEVICECHANGE", {"WORKINGORDERCODE": "WO-CURRENT", "REMARK": "设备更换"}),
    ]
    forms_by_code = {
        "WO-CURRENT": current_forms,
        "WO-HISTORY": [("RF_W_GASEOUSCHECK_CO", _form("WO-HISTORY", model="T200"))],
    }
    issues = []

    check_device_identity_consistency(
        current,
        current_forms,
        [current, history],
        forms_by_code,
        {},
        {},
        issues,
    )

    assert issues == []


def test_merge_device_history_deduplicates_orders_and_indexes_forms():
    dataset = {
        "orders": [_order("WO-CURRENT")],
        "rf_forms": {"RF_W_GASEOUSCHECK_CO": [_form("WO-CURRENT")]},
        "device_history": {
            "orders": [_order("WO-CURRENT"), _order("WO-HISTORY")],
            "rf_forms": {"RF_W_GASEOUSCHECK_CO": [_form("WO-HISTORY")]},
        },
    }

    all_orders, forms_by_code = merge_device_history(dataset)

    assert [order["WORKINGORDERCODE"] for order in all_orders] == ["WO-CURRENT", "WO-HISTORY"]
    assert [table for table, _ in forms_by_code["WO-CURRENT"]] == ["RF_W_GASEOUSCHECK_CO"]
    assert [table for table, _ in forms_by_code["WO-HISTORY"]] == ["RF_W_GASEOUSCHECK_CO"]


def test_run_rules_and_inspect_surface_device_consistency_issue(tmp_path):
    dataset = {
        "orders": [_order("WO-CURRENT")],
        "details": [
            {"WORKINGORDERCODE": "WO-CURRENT", "PROCESSSTEP": "CreateOrder", "PROCESSSTATUS": 1},
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "完成设备检查",
            },
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "PROCESSSTEP": "Review",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "复核通过",
            },
        ],
        "devices": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {"RF_W_GASEOUSCHECK_CO": [_form("WO-CURRENT", model="T100")]},
        "device_history": {
            "orders": [_order("WO-HISTORY", create_time="2026-05-01 10:00:00")],
            "rf_forms": {"RF_W_GASEOUSCHECK_CO": [_form("WO-HISTORY", model="T200")]},
        },
    }
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")

    run_result = run_ops_audit_rules(dataset_path, output_dir=tmp_path)
    inspect_result = inspect_ops_audit(
        tmp_path / "latest_finished_work_orders_deterministic_audit.json",
        dataset_path=dataset_path,
        mode="sample_rule",
        rule_id="RF_DEVICE_IDENTITY_INCONSISTENT",
    )

    assert run_result["success"] is True
    assert run_result["device_consistency_issue_count"] == 1
    assert inspect_result["success"] is True
    assert inspect_result["count"] == 1
    assert inspect_result["items"][0]["working_order_code"] == "WO-CURRENT"
