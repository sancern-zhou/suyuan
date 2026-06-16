import json
from io import BytesIO

from openpyxl import Workbook

from app.services.ops_audit.rules import o3_value_pass_xls_rules


def _xlsx(path, *, slope="0.999", intercept="-0.079", change="-0.07"):
    wb = Workbook()
    ws = wb.active
    ws["D25"] = "斜率"
    ws["F25"] = slope
    ws["D26"] = "截距(ppb)"
    ws["F26"] = intercept
    ws["F28"] = change
    wb.save(path)


def _xlsx_bytes(*, slope="0.999", intercept="-0.079", change="-0.07"):
    buffer = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws["D25"] = "斜率"
    ws["F25"] = slope
    ws["D26"] = "截距(ppb)"
    ws["F26"] = intercept
    ws["F28"] = change
    wb.save(buffer)
    return buffer.getvalue()


def _form(**overrides):
    form = {
        "WORKINGORDERCODE": "WO-001",
        "DEVICEDELIVERMODEL": "0.999",
        "DELIVERFC": "-0.079",
        "DENSITY1VALUE": "-0.07",
    }
    form.update(overrides)
    return form


def _attachment(path):
    return {
        "REFID": "WO-001",
        "TYPECODE": "RF_HY_O3ValuePass",
        "FILENAME": path.name,
        "FILEPATH": str(path),
    }


def test_o3_value_pass_xls_matching_values_adds_no_issue(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    _xlsx(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_accepts_any_xls_attachment_by_format(tmp_path):
    xls_path = tmp_path / "daily-record.xlsx"
    _xlsx(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [
            {
                "REFID": "WO-001",
                "TYPECODE": "UNRELATED_ATTACHMENT",
                "FILENAME": "daily-record.xlsx",
                "FILEPATH": str(xls_path),
            }
        ],
        [],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_missing_attachment_is_not_reported():
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [
            {
                "REFID": "WO-001",
                "TYPECODE": "RF_HY_O3ValuePass",
                "FILENAME": "传递点100.jpg",
                "FILEPATH": "/WebFiles/NewFiles/o3/point100.jpg",
            },
            {
                "REFID": "WO-001",
                "TYPECODE": "RF_HY_O3ValuePass",
                "FILENAME": "臭氧标准传递报告.pdf",
                "FILEPATH": "/WebFiles/NewFiles/o3/report.pdf",
            },
        ],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_mismatch_adds_issue(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    _xlsx(xls_path, slope="1.001")
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH"
    assert "斜率" in issues[0].message
    assert "DEVICEDELIVERMODEL" in issues[0].message
    assert "表单值0.999" in issues[0].message
    assert "XLS F25值1.001" in issues[0].message
    evidence = json.loads(issues[0].evidence)
    assert evidence["comparisons"][0]["field"] == "DEVICEDELIVERMODEL"
    assert evidence["comparisons"][0]["cell"] == "F25"
    assert evidence["comparisons"][0]["status"] == "mismatch"


def test_o3_value_pass_xls_missing_form_field_adds_issue(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    _xlsx(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form(DENSITY1VALUE=""))],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert len(issues) == 1
    evidence = json.loads(issues[0].evidence)
    assert evidence["comparisons"][0]["field"] == "DENSITY1VALUE"
    assert evidence["comparisons"][0]["cell"] == "F28"
    assert evidence["comparisons"][0]["status"] == "missing_form_value"


def test_o3_value_pass_xls_uses_file_url_when_filepath_is_unavailable(monkeypatch):
    class Response:
        content = _xlsx_bytes()

        def raise_for_status(self):
            return None

    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append((url, timeout))
        return Response()

    monkeypatch.setattr(o3_value_pass_xls_rules.requests, "get", fake_get)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [
            {
                "REFID": "WO-001",
                "TYPECODE": "RF_HY_O3ValuePass",
                "FILENAME": "o3-transfer.xlsx",
                "FILEPATH": "/WebFiles/NewFiles/o3-transfer.xlsx",
                "file_url": "http://files.example.test/WebFiles/NewFiles/o3-transfer.xlsx",
            }
        ],
        issues,
    )

    assert issues == []
    assert requested_urls == [("http://files.example.test/WebFiles/NewFiles/o3-transfer.xlsx", 30)]


def test_o3_value_pass_xls_accepts_values_in_actual_template_cells(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["D25"] = "斜率"
    ws["F25"] = "0.999"
    ws["D26"] = "截距(ppb)"
    ws["F26"] = "-0.079"
    ws["F28"] = "-0.07"
    wb.save(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_uses_d_column_labels_for_value_cells(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["D24"] = "斜率"
    ws["F24"] = "1.002"
    ws["D25"] = "截距（ppb）"
    ws["F25"] = "0.110"
    ws["F26"] = "not-the-change"
    ws["F28"] = "-0.5"
    wb.save(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [
            (
                "RF_HY_O3VALUEPASS",
                _form(
                    DEVICEDELIVERMODEL="1.002",
                    DELIVERFC="0.110",
                    DENSITY1VALUE="-0.5",
                ),
            )
        ],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_accepts_change_value_within_three_rows_after_intercept(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["D25"] = "斜率"
    ws["F25"] = "0.999"
    ws["D26"] = "截距(ppb)"
    ws["F26"] = "-0.079"
    ws["F27"] = "not-the-change"
    ws["F28"] = "-0.5"
    wb.save(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form(DENSITY1VALUE="-0.5"))],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert issues == []


def test_o3_value_pass_xls_does_not_use_fixed_cells_without_d_column_labels(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["F25"] = "0.999"
    ws["F26"] = "-0.079"
    ws["F28"] = "-0.07"
    wb.save(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [("RF_HY_O3VALUEPASS", _form())],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert len(issues) == 1
    evidence = json.loads(issues[0].evidence)
    statuses = {comparison["field"]: comparison["status"] for comparison in evidence["comparisons"]}
    assert statuses == {
        "DEVICEDELIVERMODEL": "missing_xls_value",
        "DELIVERFC": "missing_xls_value",
        "DENSITY1VALUE": "missing_xls_value",
    }


def test_o3_value_pass_xls_matches_using_form_precision_and_percent_scale(tmp_path):
    xls_path = tmp_path / "o3-transfer.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["D24"] = "斜率"
    ws["F24"] = 0.9994584484828917
    ws["D25"] = "截距(ppb)"
    ws["F25"] = -0.11881566910229442
    ws["F27"] = -0.010978043912175658
    wb.save(xls_path)
    issues = []

    o3_value_pass_xls_rules.check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "WO-001"},
        [
            (
                "RF_HY_O3VALUEPASS",
                _form(
                    DEVICEDELIVERMODEL="0.999",
                    DELIVERFC="-0.119",
                    DENSITY1VALUE="-1.10",
                ),
            )
        ],
        [],
        [_attachment(xls_path)],
        issues,
    )

    assert issues == []
