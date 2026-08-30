import json

from app.services.ops_audit.rules.rf_humidity_rules import check_rf_environment_humidity_values


def test_quarter_gaseous_flow_humidity_above_80_is_reported():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606161781605828953"}
    form = {
        "WORKINGORDERCODE": "CH2606161781605828953",
        "Humidity": "82",
    }

    check_rf_environment_humidity_values(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert [issue.rule_id for issue in issues] == ["RF_Q_GASEOUS_FLOW_ENV_HUMIDITY_OUT_OF_RANGE"]
    assert "室内湿度82.0%超出0-80%" in issues[0].message
    evidence = json.loads(issues[0].evidence)
    assert evidence["field"] == "Humidity"
    assert evidence["value"] == 82.0


def test_quarter_gaseous_flow_humidity_at_80_is_allowed():
    issues = []
    order = {"WORKINGORDERCODE": "WO-HUMIDITY-80"}
    form = {
        "WORKINGORDERCODE": "WO-HUMIDITY-80",
        "Humidity": "80%",
    }

    check_rf_environment_humidity_values(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert issues == []


def test_monthly_gaseous_calibration_humidity_above_80_is_reported():
    issues = []
    order = {"WORKINGORDERCODE": "CH2607161784189047348"}
    form = {
        "WORKINGORDERCODE": "CH2607161784189047348",
        "SD": "84.5",
    }

    check_rf_environment_humidity_values(
        order,
        [("RF_M_GASEOUSCALIDEVICECHECK", form)],
        issues,
    )

    assert [issue.rule_id for issue in issues] == [
        "RF_M_GASEOUS_CALIDEVICE_ENV_HUMIDITY_OUT_OF_RANGE"
    ]
    assert "月度气态校准设备检查室内湿度84.5%超出0-80%" in issues[0].message
    evidence = json.loads(issues[0].evidence)
    assert evidence["field"] == "SD"
    assert evidence["value"] == 84.5


def test_monthly_gaseous_calibration_humidity_at_80_is_allowed():
    issues = []
    order = {"WORKINGORDERCODE": "WO-MONTHLY-HUMIDITY-80"}
    form = {"WORKINGORDERCODE": "WO-MONTHLY-HUMIDITY-80", "SD": "80"}

    check_rf_environment_humidity_values(
        order,
        [("RF_M_GASEOUSCALIDEVICECHECK", form)],
        issues,
    )

    assert issues == []
