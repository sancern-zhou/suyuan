import json

from app.services.ops_audit.rules.rf_enum_rules import check_rf_enum_values


def test_pm_flow_calibration_not_selected_with_post_values_is_reported():
    issues = []
    order = {"WORKINGORDERCODE": "CH2607171784254636644"}
    form = {
        "IsCalibrate": "否",
        "Next_S": "16.66",
        "Next_A": "16.76",
        "Next_B": "16.67",
        "Next_C": "-0.54",
    }

    check_rf_enum_values(order, [("RF_TW_PmFlowCalibrate", form)], issues)

    matched = [item for item in issues if item.rule_id == "RF_PM_FLOW_CALIBRATION_STATE_MISMATCH"]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    evidence = json.loads(matched[0].evidence)
    assert evidence["is_calibrate"] == "否"
    assert evidence["post_calibration_fields"]["Next_A"] == "16.76"


def test_pm_flow_calibration_not_selected_with_placeholders_is_allowed():
    issues = []
    form = {
        "IsCalibrate": "0",
        "Next_S": "/",
        "Next_A": "未校准",
        "Next_B": "",
        "Next_C": "-",
    }

    check_rf_enum_values({"WORKINGORDERCODE": "WO-EMPTY-NEXT"}, [("RF_TW_PmFlowCalibrate", form)], issues)

    assert not [item for item in issues if item.rule_id == "RF_PM_FLOW_CALIBRATION_STATE_MISMATCH"]


def test_pm_flow_calibration_selected_with_post_values_is_allowed():
    issues = []
    form = {"IsCalibrate": "是", "Next_A": "16.76", "Next_B": "16.67", "Next_C": "-0.54"}

    check_rf_enum_values({"WORKINGORDERCODE": "WO-CALIBRATED"}, [("RF_TW_PmFlowCalibrate", form)], issues)

    assert not [item for item in issues if item.rule_id == "RF_PM_FLOW_CALIBRATION_STATE_MISMATCH"]
