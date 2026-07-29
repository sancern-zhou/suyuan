import json

from openpyxl import Workbook

from app.services.ops_audit.rules import o3_value_pass_xls_rules as rules
from app.services.ops_work_order_audit_engine import audit_dataset


def _workbook(
    path,
    *,
    section="上级臭氧传递标准：",
    model="49ips",
    device_number="N.A.",
    serial_number="CM26037055",
    date_label="传递日期：",
    transfer_date="2026-3-4 to 2026-3-6",
    formula_label="传递公式：",
    formula="Y=1.00338X+0.20(ppb)",
    expiry_label="传递有效期限：",
    expiry_date="2027-3-6",
):
    workbook = Workbook()
    sheet = workbook.active
    sheet["D25"], sheet["F25"] = "斜率", "0.999"
    sheet["D26"], sheet["F26"] = "截距(ppb)", "-0.079"
    sheet["F28"] = "-0.07"
    sheet["A16"] = section
    sheet["A17"], sheet["C17"], sheet["D17"], sheet["G17"] = "型号：", model, date_label, transfer_date
    sheet["A18"], sheet["C18"], sheet["D18"], sheet["G18"] = "设备号：", device_number, formula_label, formula
    sheet["A19"], sheet["C19"], sheet["D19"], sheet["G19"] = "序列号：", serial_number, expiry_label, expiry_date
    workbook.save(path)


def _form(code="WO-1", **overrides):
    form = {
        "WORKINGORDERCODE": code,
        "DEVICEDELIVERMODEL": "0.999",
        "DELIVERFC": "-0.079",
        "DENSITY1VALUE": "-0.07",
        "DELIVER6VALUE": "49IPS",
        "DELIVERFROM6VALUE": "N.A",
        "AVALUE": "CM26037055",
        "WORKDENSITY6VALUE": "2026/03/04-06",
        "DELIVERTO6VALUE": "y = 1.00338 (x) + 0.20",
        "BVALUE": "3/6/2027",
    }
    form.update(overrides)
    return form


def _attachment(path):
    return {
        "REFID": "WO-1",
        "TYPECODE": "RF_HY_O3ValuePass",
        "FILENAME": path.name,
        "FILEPATH": str(path),
    }


def _check(form, attachments):
    issues = []
    rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": form["WORKINGORDERCODE"]},
        [("RF_HY_O3VALUEPASS", form)],
        [],
        attachments,
        issues,
    )
    return issues


def test_upper_standard_fields_match_after_text_date_and_formula_normalization(tmp_path):
    path = tmp_path / "o3.xlsx"
    _workbook(path)

    assert _check(_form(), [_attachment(path)]) == []


def test_upper_standard_device_number_mismatch_is_deterministic(tmp_path):
    path = tmp_path / "o3.xlsx"
    _workbook(path, serial_number="CM20457343")

    issues = _check(
        _form(DELIVERFROM6VALUE="CM20457343", AVALUE="CM20457343"),
        [_attachment(path)],
    )

    assert len(issues) == 1
    assert issues[0].rule_id == rules.RULE_ID
    evidence = json.loads(issues[0].evidence)
    comparison = next(item for item in evidence["comparisons"] if item["field"] == "DELIVERFROM6VALUE")
    assert comparison["status"] == "mismatch"
    assert comparison["xls_value"] == "N.A."


def test_reference_photometer_t703_layout_does_not_assume_49ips(tmp_path):
    path = tmp_path / "t703.xlsx"
    _workbook(
        path,
        section="参考光电仪：",
        model="T703",
        device_number="569",
        serial_number="569",
        date_label="认证日期：",
        transfer_date="2026-02-25",
        formula_label="认证公式：",
        formula="Y=1.0017X-0.39(ppb)",
        expiry_label="认证有效期限：",
        expiry_date="2027-02-24",
    )

    form = _form(
        DELIVER6VALUE="T703",
        DELIVERFROM6VALUE="569",
        AVALUE="569",
        WORKDENSITY6VALUE="2026/2/25",
        DELIVERTO6VALUE="y=1.00170x-0.390",
        BVALUE="2027/2/24",
    )
    assert _check(form, [_attachment(path)]) == []


def test_missing_xls_is_manual_review_with_attachment_paths():
    issues = _check(
        _form(),
        [
            {
                "REFID": "WO-1",
                "TYPECODE": "RF_HY_O3ValuePass",
                "FILENAME": "臭氧标准传递报告.pdf",
                "FILEPATH": "/WebFiles/o3/report.pdf",
            }
        ],
    )

    assert len(issues) == 1
    assert issues[0].rule_id == rules.MISSING_XLS_REVIEW_RULE_ID
    evidence = json.loads(issues[0].evidence)
    assert evidence["needs_manual_review"] is True
    assert evidence["available_attachments"][0]["source_path"] == "/WebFiles/o3/report.pdf"


def test_history_conflict_reports_alternatives_without_canonical_value():
    forms_by_code = {
        "WO-A": [("RF_HY_O3VALUEPASS", _form("WO-A"))],
        "WO-B": [
            (
                "RF_HY_O3VALUEPASS",
                _form("WO-B", DELIVER6VALUE="TE", DELIVERFROM6VALUE="49ips"),
            )
        ],
    }

    result = rules.build_o3_upper_standard_history_conflicts(forms_by_code, {"WO-A", "WO-B"})

    assert set(result) == {"WO-A", "WO-B"}
    evidence = json.loads(result["WO-A"][0].evidence)
    assert "canonical_value" not in evidence
    assert {tuple(item["order_codes"]) for item in evidence["alternatives"]} == {("WO-A",), ("WO-B",)}


def test_history_conflict_requires_complete_fingerprint_and_current_order():
    incomplete = {
        "WO-A": [("RF_HY_O3VALUEPASS", _form("WO-A", AVALUE=""))],
        "WO-B": [
            (
                "RF_HY_O3VALUEPASS",
                _form("WO-B", AVALUE="", DELIVER6VALUE="TE", DELIVERFROM6VALUE="49ips"),
            )
        ],
    }
    assert rules.build_o3_upper_standard_history_conflicts(incomplete, {"WO-A", "WO-B"}) == {}

    complete = {
        "WO-CURRENT": [("RF_HY_O3VALUEPASS", _form("WO-CURRENT"))],
        "WO-HISTORY": [
            (
                "RF_HY_O3VALUEPASS",
                _form("WO-HISTORY", DELIVER6VALUE="TE", DELIVERFROM6VALUE="49ips"),
            )
        ],
    }
    result = rules.build_o3_upper_standard_history_conflicts(complete, {"WO-CURRENT"})
    assert set(result) == {"WO-CURRENT"}


def test_audit_dataset_attaches_history_conflict_to_current_order():
    current = _form("WO-CURRENT")
    historical = _form("WO-HISTORY", DELIVER6VALUE="TE", DELIVERFROM6VALUE="49ips")
    order = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "1502",
        "CREATETIME": "2026-06-25 10:00:00",
        "FINISHTIME": "2026-06-25 18:00:00",
    }
    dataset = {
        "orders": [order],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "stations": [],
        "devices": [],
        "rf_forms": {"RF_HY_O3VALUEPASS": [current]},
        "device_history": {
            "orders": [{**order, "WORKINGORDERCODE": "WO-HISTORY", "CREATETIME": "2026-03-25 10:00:00"}],
            "rf_forms": {"RF_HY_O3VALUEPASS": [historical]},
        },
    }

    result = audit_dataset(dataset, enable_visual=False)

    record = result["records"][0]
    assert len(
        [issue for issue in record["issues"] if issue["rule_id"] == rules.HISTORY_CONFLICT_REVIEW_RULE_ID]
    ) == 1
