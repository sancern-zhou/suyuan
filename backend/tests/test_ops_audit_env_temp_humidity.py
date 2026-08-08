from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields


def test_env_temp_humidity_uses_order_level_completed_pair():
    issues = []
    check_rf_required_fields(
        {"WORKINGORDERCODE": "CH2605181779091511878"},
        [
            (
                "RF_Q_GaseousFlowCheck",
                {
                    "WORKINGORDERCODE": "CH2605181779091511878",
                    "Temperature": "29",
                    "Humidity": "36.5",
                },
            ),
            (
                "RF_HY_GASEOUSCALIDEVICECHECK",
                {
                    "WORKINGORDERCODE": "CH2605181779091511878",
                    "WD": "",
                    "SD": "",
                },
            ),
        ],
        issues,
    )

    assert not any(issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY" for issue in issues)


def test_env_temp_humidity_reports_when_no_completed_pair_exists():
    issues = []
    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-MISSING-ENV"},
        [
            (
                "RF_HY_GASEOUSCALIDEVICECHECK",
                {
                    "WORKINGORDERCODE": "WO-MISSING-ENV",
                    "WD": "",
                    "SD": "/",
                },
            )
        ],
        issues,
    )

    assert any(issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY" for issue in issues)


def test_env_temp_humidity_skips_not_applicable_device_records():
    issues = []
    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-NO-VISIBILITY"},
        [
            (
                "RF_HY_VISIBILITYCALI",
                {
                    "WORKINGORDERCODE": "WO-NO-VISIBILITY",
                    "TEMP": "/",
                    "REMARK": "站点无该设备",
                },
            )
        ],
        issues,
    )

    assert not any(issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY" for issue in issues)
