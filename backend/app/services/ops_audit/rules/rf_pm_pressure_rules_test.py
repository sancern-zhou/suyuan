import json

from app.services.ops_audit.config import review_stage_for_rule
from app.services.ops_audit.rules.rf_pm_pressure_rules import check_rf_pm_pressure_values


def test_pm_pressure_unit_mismatch_with_calibration_situation_needs_semantic_review():
    issues = []
    order = {
        "WORKINGORDERCODE": "CH2606051780657104456",
        "ORDERTITLE": "PM10备机上架测试",
        "ORDERCONTENT": "PM10备机上架测试",
    }
    form = {
        "WORKINGORDERCODE": "CH2606051780657104456",
        "PM10CHECKPRES1VALUE": "99.6",
        "PM10CHECKPRES2VALUE": "99.2",
        "PM10CHECKPRES3VALUE": "0.4",
        "PM10CHECKPRES4VALUE": "",
        "PM25CHECKPRES1VALUE": "0",
        "PM25CHECKPRES2VALUE": "0",
        "PM25CHECKPRES3VALUE": "0.0",
        "PM25CHECKPRES4VALUE": "无需检查",
    }

    check_rf_pm_pressure_values(order, [("RF_Q_PMPRESSURE", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_PRESSURE_UNIT_MISMATCH"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["needs_semantic_review"] is True
    assert evidence["semantic_review_basis"] == "颗粒物气压数值异常但对应校准情况字段有说明，需结合说明和工单标题/内容复核。"
    assert evidence["order_context"] == {
        "title": "PM10备机上架测试",
        "content": "PM10备机上架测试",
    }
    assert evidence["violations"][0]["calibration_situation_field"] == "PM25CHECKPRES4VALUE"
    assert evidence["violations"][0]["calibration_situation"] == "无需检查"


def test_pm_pressure_unit_mismatch_without_calibration_situation_is_deterministic_issue():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-PM25-BLANK-SITUATION",
        "ORDERTITLE": "颗粒物压力检查",
        "ORDERCONTENT": "",
    }
    form = {
        "WORKINGORDERCODE": "WO-PM25-BLANK-SITUATION",
        "PM25CHECKPRES1VALUE": "0",
        "PM25CHECKPRES2VALUE": "0",
        "PM25CHECKPRES3VALUE": "0.0",
        "PM25CHECKPRES4VALUE": "",
    }

    check_rf_pm_pressure_values(order, [("RF_Q_PMPRESSURE", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_PRESSURE_UNIT_MISMATCH"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert "needs_semantic_review" not in evidence
    assert evidence["violations"][0]["calibration_situation_field"] == "PM25CHECKPRES4VALUE"
    assert evidence["violations"][0]["calibration_situation"] == ""


def test_pm_temp_range_out_of_range_with_calibration_situation_needs_semantic_review():
    issues = []
    order = {
        "WORKINGORDERCODE": "CH2606021780356188816",
        "ORDERTITLE": "颗粒物压力检查",
        "ORDERCONTENT": "颗粒物压力检查记录表（季度）",
    }
    form = {
        "WORKINGORDERCODE": "CH2606021780356188816",
        "PM25CHECKTEMP1VALUE": "53.94",
        "PM25CHECKTEMP2VALUE": "36.4",
        "PM25CHECKTEMP3VALUE": "17.5",
        "PM25CHECKTEMP4VALUE": "该仪器无校准功能作参考",
    }

    check_rf_pm_pressure_values(order, [("RF_Q_PMPRESSURE", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TEMP_ERROR_OUT_OF_RANGE"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["needs_semantic_review"] is True
    assert evidence["semantic_review_basis"] == "颗粒物温度误差超限但对应校准情况字段有说明，需结合说明和工单标题/内容复核。"
    assert evidence["order_context"] == {
        "title": "颗粒物压力检查",
        "content": "颗粒物压力检查记录表（季度）",
    }
    assert evidence["violations"][0]["calibration_situation_field"] == "PM25CHECKTEMP4VALUE"
    assert evidence["violations"][0]["calibration_situation"] == "该仪器无校准功能作参考"
    assert review_stage_for_rule("RF_PM_TEMP_ERROR_OUT_OF_RANGE") == "deterministic"


def test_pm_temp_range_out_of_range_without_calibration_situation_is_deterministic_issue():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-PM25-TEMP-BLANK-SITUATION",
        "ORDERTITLE": "颗粒物压力检查",
        "ORDERCONTENT": "",
    }
    form = {
        "WORKINGORDERCODE": "WO-PM25-TEMP-BLANK-SITUATION",
        "PM25CHECKTEMP1VALUE": "53.94",
        "PM25CHECKTEMP2VALUE": "36.4",
        "PM25CHECKTEMP3VALUE": "17.5",
        "PM25CHECKTEMP4VALUE": "",
    }

    check_rf_pm_pressure_values(order, [("RF_Q_PMPRESSURE", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TEMP_ERROR_OUT_OF_RANGE"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert "needs_semantic_review" not in evidence
    assert evidence["violations"][0]["calibration_situation_field"] == "PM25CHECKTEMP4VALUE"
    assert evidence["violations"][0]["calibration_situation"] == ""
