"""Source-view alignment tests for RF weekly range profiles.

Every threshold below is taken from the Guangdong platform views
(D:/广东运维平台/trunk/SummerFresh.MVC/Views/ReportForms/*.cshtml). Keep the
case list in sync with projects/guangdong/docs/audit-rule-source-governance.md.
"""

import pytest

from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values


def _issues(table, brand, pollutant, field, value, model=""):
    form = {
        "WORKINGORDERCODE": "WO-SOURCE-ALIGN",
        "DEVICEBRAND": brand,
        "POLLUTANTTYPE": pollutant,
    }
    if model:
        form["DEVICEMODEL"] = model
    if field:
        form[field] = value
    issues = []
    check_rf_range_values({"WORKINGORDERCODE": "WO-SOURCE-ALIGN"}, [(table, form)], issues)
    return issues


def _has(issues, rule_id="RF_RANGE_OUT_OF_SPEC"):
    return any(issue.rule_id == rule_id for issue in issues)


@pytest.mark.parametrize(
    "table,brand,pollutant,field,value,expected",
    [
        # CO: RF_W_GASEOUSCHECK_CO.cshtml:165-286
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "JGCHECKVALUE", "-200", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "JGCHECKVALUE", "500", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "JGCHECKVALUE", "-201", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "JGCHECKVALUE", "501", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "CYLLCHECKVALUE", "720", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "CYLLCHECKVALUE", "880", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "CYLLCHECKVALUE", "719", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "CYLLCHECKVALUE", "881", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "GSWDCHECKVALUE", "47", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "GSWDCHECKVALUE", "49", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "GSWDCHECKVALUE", "46", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "YLCHECKVALUE", "0.85", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "YLCHECKVALUE", "1.15", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "YLCHECKVALUE", "0.84", True),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "GYCHECKVALUE", "2V", False),
        ("RF_W_GASEOUSCHECK_CO", "FPI", "CO", "GYCHECKVALUE", "4.5V", True),
        ("RF_W_GASEOUSCHECK_CO", "天虹", "CO", "GYCHECKVALUE", "2000", False),
        ("RF_W_GASEOUSCHECK_CO", "天虹", "CO", "GYCHECKVALUE", "10000", False),
        ("RF_W_GASEOUSCHECK_CO", "天虹", "CO", "GYCHECKVALUE", "1999", True),
        ("RF_W_GASEOUSCHECK_CO", "XH", "CO", "FYCHECKVALUE", "48", False),
        ("RF_W_GASEOUSCHECK_CO", "XH", "CO", "FYCHECKVALUE", "46", True),
        # NOX: RF_W_GASEOUSCHECK_NOX.cshtml:212-395
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLCHECKVALUE", "350", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLCHECKVALUE", "650", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLCHECKVALUE", "349", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLIANGCHECKVALUE", "72", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLIANGCHECKVALUE", "88", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYLLIANGCHECKVALUE", "71", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "PMTCHECKVALUE", "1.5V", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "PMTCHECKVALUE", "4.096V", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "PMTCHECKVALUE", "1.4V", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "GYCHECKVALUE", "450", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "GYCHECKVALUE", "900", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "GYCHECKVALUE", "901", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYCHECKVALUE", "49", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYCHECKVALUE", "51", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYCHECKVALUE", "48", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYSHICHECKVALUE", "0", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYSHICHECKVALUE", "15", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "FYSHICHECKVALUE", "16", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYYLCHECKVALUE", "0", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYYLCHECKVALUE", "15", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "CYYLCHECKVALUE", "-1", True),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "NOXYLCHECKVALUE", "0.85", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "NOXYLCHECKVALUE", "1.15", False),
        ("RF_W_GASEOUSCHECK_NOX", "FPI", "NOX", "NOXYLCHECKVALUE", "0.7", True),
        ("RF_W_GASEOUSCHECK_NOX", "XH", "NOX", "FYSHICHECKVALUE", "20", False),
        ("RF_W_GASEOUSCHECK_NOX", "XH", "NOX", "FYSHICHECKVALUE", "5.8", True),
        # O3: RF_W_GaseousCheck_O3.cshtml:170-265
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "CYLLCHECKVALUE", "720", False),
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "CYLLCHECKVALUE", "880", False),
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "CYLLCHECKVALUE", "1000", True),
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "YLCHECKVALUE", "0.85", False),
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "YLCHECKVALUE", "1.15", False),
        ("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "YLCHECKVALUE", "0.7", True),
        # SO2: RF_W_GaseousCheck_SO2.cshtml:212-336
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "CYLLCHECKVALUE", "580", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "CYLLCHECKVALUE", "720", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "CYLLCHECKVALUE", "800", True),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "PMTCHECKVALUE", "1.5V", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "PMTCHECKVALUE", "1.0V", True),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "ZWDCHECKVALUE", "4.096V", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "ZWDCHECKVALUE", "1.0V", True),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "YLCHECKVALUE", "0.85", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "YLCHECKVALUE", "0.7", True),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "FYCHECKVALUE", "45", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "FYCHECKVALUE", "55", False),
        ("RF_W_GASEOUSCHECK_SO2", "FPI", "SO2", "FYCHECKVALUE", "44", True),
        # PM: RF_W_PmCheck.cshtml:60-75 (no brand distinction)
        ("RF_W_PMCHECK", "THERMO", "PM10", "MAINFLOWVALUE", "16.0", False),
        ("RF_W_PMCHECK", "THERMO", "PM10", "MAINFLOWVALUE", "18.0", True),
        ("RF_W_PMCHECK", "FPI", "PM10", "MAINFLOWVALUE", "16.0", False),
        ("RF_W_PMCHECK", "LD", "PM10", "MAINFLOWVALUE", "16.0", False),
        ("RF_W_PMCHECK", "FPI", "PM10", "AIRTEMPVALUE", "50", False),
        ("RF_W_PMCHECK", "FPI", "PM10", "AIRTEMPVALUE", "51", True),
        ("RF_W_PMCHECK", "", "PM10", "MAINFLOWVALUE", "16.0", False),
    ],
)
def test_source_view_thresholds(table, brand, pollutant, field, value, expected):
    issues = _issues(table, brand, pollutant, field, value)
    assert _has(issues) is expected, (table, brand, field, value, issues)


@pytest.mark.parametrize(
    "brand,expected_range_field",
    [
        ("聚光", "JGCHECKVALUE"),
        ("聚光科技", "JGCHECKVALUE"),
        ("FPI", "JGCHECKVALUE"),
    ],
)
def test_co_brand_alias_maps_chinese_juguang_to_fpi(brand, expected_range_field):
    issues = _issues("RF_W_GASEOUSCHECK_CO", brand, "CO", expected_range_field, "100")
    assert issues == []


@pytest.mark.parametrize(
    "brand,expected",
    [
        ("聚光", "FPI"),
        ("聚光科技", "FPI"),
        ("FPI", "FPI"),
        ("天虹", "TH"),
        ("武汉天虹", "TH"),
        ("大西比", "DASIBI"),
        ("Dasibi", "DASIBI"),
        ("先河环保", "XH"),
        ("先河", "XH"),
        ("赛默飞", "THERMO"),
        ("热电", "THERMO"),
        ("力合", "LD"),
    ],
)
def test_common_brand_aliases_resolve(brand, expected):
    from app.services.ops_audit.rules import rf_range_rules

    assert rf_range_rules._normalize_profile_brand(brand, rf_range_rules.COMMON_BRAND_ALIASES) == expected


def test_submitted_value_without_brand_range_reports_technical_diagnostic():
    issues = _issues("RF_W_GASEOUSCHECK_CO", "LD", "CO", "GYCHECKVALUE", "3000")
    assert not _has(issues)
    diagnostics = [issue for issue in issues if issue.rule_id == "RF_RANGE_BRAND_PROFILE_UNCOVERED"]
    assert len(diagnostics) == 1
    assert "测量信号" in diagnostics[0].message


def test_brand_model_conflict_reports_technical_diagnostic_instead_of_range_issue():
    issues = _issues("RF_W_GASEOUSCHECK_O3", "FPI", "O3", "GYCHECKVALUE", "2.5V", model="49i")
    assert not _has(issues)
    assert _has(issues, "RF_RANGE_BRAND_PROFILE_UNCOVERED")


def test_empty_brand_uses_default_pm_range():
    issues = _issues("RF_W_PMCHECK", "", "PM10", "AIRTEMPVALUE", "51")
    assert _has(issues)
