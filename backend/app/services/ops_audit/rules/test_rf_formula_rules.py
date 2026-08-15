import json

from app.services.ops_audit.rules.rf_calibration_date_rules import check_rf_calibration_dates
from app.services.ops_audit.rules.rf_formula_rules import check_rf_formula_values


def test_quarter_gaseous_flow_target_point_mismatch_detects_wrong_standard_point():
    issues = []
    order = {"WORKINGORDERCODE": "CH2605271779848396378"}
    form = {
        "WORKINGORDERCODE": "CH2605271779848396378",
        "DF_Valuve_35": "2000",
        "RF_Valuve_35": "2021",
        "DF_Valuve_20": "20",
        "RF_Valuve_20": "19.98",
    }

    check_rf_formula_values(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    matching = [issue for issue in issues if issue.rule_id == "RF_Q_GASEOUS_FLOW_TARGET_POINT_MISMATCH"]
    assert len(matching) == 1
    assert "35" in matching[0].message
    evidence = json.loads(matching[0].evidence)
    assert evidence["violations"][0]["field"] == "DF_Valuve_35"
    assert evidence["violations"][0]["expected_target"] == 3500


def test_quarter_gaseous_flow_target_point_mismatch_detects_wrong_zero_point():
    issues = []
    order = {"WORKINGORDERCODE": "CH2605261779792743082"}
    form = {
        "WORKINGORDERCODE": "CH2605261779792743082",
        "DF_Valuve_35": "3500",
        "RF_Valuve_35": "3892",
        "DF_Valuve_20": "10",
        "RF_Valuve_20": "10.84",
    }

    check_rf_formula_values(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    matching = [issue for issue in issues if issue.rule_id == "RF_Q_GASEOUS_FLOW_TARGET_POINT_MISMATCH"]
    assert len(matching) == 1
    evidence = json.loads(matching[0].evidence)
    df20 = next(item for item in evidence["violations"] if item["field"] == "DF_Valuve_20")
    assert df20["expected_target"] == 20


def test_quarter_gaseous_flow_target_point_allows_correct_selected_points():
    issues = []
    order = {"WORKINGORDERCODE": "WO-CORRECT-POINTS"}
    form = {
        "WORKINGORDERCODE": "WO-CORRECT-POINTS",
        "DF_Valuve_60": "6000",
        "RF_Valuve_60": "6048",
        "DF_Valuve_50": "50",
        "RF_Valuve_50": "51.35",
    }

    check_rf_formula_values(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert [issue for issue in issues if issue.rule_id == "RF_Q_GASEOUS_FLOW_TARGET_POINT_MISMATCH"] == []


def test_calibration_expiry_date_is_valid_for_the_entire_same_day():
    order = {
        "WORKINGORDERCODE": "CH2607091783605182246",
        "STATIONID": "1724",
        "CREATETIME": "2026-07-09 21:53:02",
    }
    form = {
        "WORKINGORDERCODE": "CH2607091783605182246",
        "STATIONID": "1724",
        "CHECKDATE": "2026-07-09 15:15:00",
        "F_PrevDate": "2026-06-25 00:00:00",
        "F_NextDate": "2026-07-09 00:00:00",
    }
    issues = []

    check_rf_calibration_dates(order, [("RF_TW_PmFlowCalibrate", form)], issues)

    assert issues == []


def test_expired_calibration_evidence_and_message_include_human_readable_dates():
    order = {
        "WORKINGORDERCODE": "CH2607091783605182246",
        "STATIONID": "1724",
        "CREATETIME": "2026-07-09 21:53:02",
    }
    form = {
        "WORKINGORDERCODE": "CH2607091783605182246",
        "STATIONID": "1724",
        "CHECKDATE": "2026-07-09 15:15:00",
        "F_PrevDate": "2026-06-25 00:00:00",
        "F_NextDate": "2026-07-08 00:00:00",
    }
    issues = []

    check_rf_calibration_dates(order, [("RF_TW_PmFlowCalibrate", form)], issues)

    assert len(issues) == 1
    assert issues[0].message == (
        "RF表单校准有效期异常: 流量计校准有效期至2026-07-08 00:00:00，"
        "本次检查时间为2026-07-09 15:15:00"
    )
    violation = json.loads(issues[0].evidence)["violations"][0]
    assert violation["reason"] == "not_after_reference"
    assert violation["description"] == (
        "流量计校准有效期至2026-07-08 00:00:00，"
        "本次检查时间为2026-07-09 15:15:00"
    )
