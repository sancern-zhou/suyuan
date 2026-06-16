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
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["missing_temperature"] == ["TEMP"]
    assert evidence["missing_humidity"] == ["DAMP"]
    assert evidence["needs_semantic_review"] is False


def test_env_temp_humidity_empty_with_remark_needs_semantic_review():
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
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["missing_temperature"] == ["TEMP"]
    assert evidence["missing_humidity"] == ["DAMP"]
    assert evidence["needs_semantic_review"] is True
    assert evidence["remark_candidates"] == {"REMARK": "无能见度分析仪"}
