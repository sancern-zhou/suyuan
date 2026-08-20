import json

from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields


def test_pm_1405_teom_placeholder_message_explains_required_field_reason():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606231782181721442"}
    form = {
        "WORKINGORDERCODE": "CH2606231782181721442",
        "POLLUTANTTYPE": "PM2.5",
        "DEVICEMODEL": "1405",
        "TAPEUSAGEDISPOSAL": "足够使用一周",
        "TEOMMEMBRANEDISPOSAL": "/",
    }

    check_rf_required_fields(order, [("RF_W_PMCHECK", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TAPE_USAGE_INVALID"]
    assert len(matched) == 1
    assert matched[0].message == (
        "颗粒物周检TEOM滤膜负载及处置情况为空或为/，"
        "DEVICEMODEL=1405应填写TEOM滤膜负载及处置情况"
    )
    evidence = json.loads(matched[0].evidence)
    assert evidence["field"] == "TEOMMEMBRANEDISPOSAL"
    assert evidence["instrument_type"] == "teom_filter"
    assert evidence["needs_semantic_review"] is False
    assert evidence["problem_reason"] == (
        "DEVICEMODEL=1405按TEOM/振荡天平类设备审核，"
        "应填写TEOM滤膜负载及处置情况；当前TEOMMEMBRANEDISPOSAL为空或为/，"
        "无法判断滤膜负载或处置状态。"
    )


def test_pm_paper_tape_placeholder_message_names_paper_tape_field():
    issues = []
    order = {"WORKINGORDERCODE": "WO-PAPER-TAPE"}
    form = {
        "WORKINGORDERCODE": "WO-PAPER-TAPE",
        "POLLUTANTTYPE": "PM10",
        "DEVICEMODEL": "SHARP5030",
        "TAPEUSAGEDISPOSAL": "/",
        "TEOMMEMBRANEDISPOSAL": "/",
    }

    check_rf_required_fields(order, [("RF_W_PMCHECK", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TAPE_USAGE_INVALID"]
    assert len(matched) == 1
    assert matched[0].message == "颗粒物周检纸带使用量及处置情况为空或为/，非1405颗粒物仪器应填写纸带使用量及处置情况"


def test_pm_1405_substantive_paper_tape_value_is_not_applicable():
    issues = []
    order = {"WORKINGORDERCODE": "WO-TEOM-PAPER-TAPE"}
    form = {
        "WORKINGORDERCODE": "WO-TEOM-PAPER-TAPE",
        "POLLUTANTTYPE": "PM10",
        "DEVICEMODEL": "1405",
        "TAPEUSAGEDISPOSAL": "已更换纸带",
        "TEOMMEMBRANEDISPOSAL": "滤膜负载 30%，无需更换",
    }

    check_rf_required_fields(order, [("RF_W_PMCHECK", form)], issues)

    matched = [
        issue for issue in issues if issue.rule_id == "RF_PM_PAPER_TAPE_NOT_APPLICABLE_FILLED"
    ]
    assert len(matched) == 1
    assert "1405/TEOM设备不使用纸带" in matched[0].message
    evidence = json.loads(matched[0].evidence)
    assert evidence["field"] == "TAPEUSAGEDISPOSAL"


def test_visibility_env_fields_allow_not_configured_device_remark():
    issues = []
    order = {"WORKINGORDERCODE": "WO-NO-VISIBILITY"}
    form = {
        "WORKINGORDERCODE": "WO-NO-VISIBILITY",
        "TEMP": "/",
        "DAMP": "/",
        "REMARK": "站点无能见度分析仪。",
    }

    check_rf_required_fields(order, [("RF_HY_VISIBILITYCALI", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY"]
    assert matched == []
