import json

from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields


def test_env_temp_humidity_empty_without_remark_is_direct_issue():
    issues = []

    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-ENV-EMPTY"},
        [
            (
                "RF_HY_VISIBILITYCALI",
                {
                    "WORKINGORDERCODE": "WO-ENV-EMPTY",
                    "TEMP": "/",
                    "DAMP": "/",
                    "REMARK": "",
                },
            )
        ],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY"]
    assert len(matched) == 2
    by_dimension = {
        json.loads(issue.evidence)["missing_dimension"]: issue
        for issue in matched
    }
    assert by_dimension["temperature"].field == "rf.RF_HY_VISIBILITYCALI.TEMP"
    assert by_dimension["temperature"].message == "RF表单温度字段(TEMP)未填"
    assert by_dimension["humidity"].field == "rf.RF_HY_VISIBILITYCALI.DAMP"
    assert by_dimension["humidity"].message == "RF表单湿度字段(DAMP)未填"
    assert all(json.loads(issue.evidence)["needs_semantic_review"] is False for issue in matched)


def test_env_temp_humidity_empty_with_no_visibility_analyzer_remark_is_exempt():
    issues = []

    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-ENV-REMARK"},
        [
            (
                "RF_HY_VISIBILITYCALI",
                {
                    "WORKINGORDERCODE": "WO-ENV-REMARK",
                    "TEMP": "/",
                    "DAMP": "/",
                    "REMARK": "无能见度分析仪",
                },
            )
        ],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY"]
    assert matched == []
