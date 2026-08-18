import json
from dataclasses import asdict

import pytest

from app.services.ops_audit.issue_linking import issue_link_metadata
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.rf_abnormal_remark_rules import check_rf_abnormal_remarks


def _base_issue(rule_id: str, table: str, field: str, message: str, evidence: dict) -> Issue:
    return Issue(
        rule_id=rule_id,
        category="结果合理性",
        severity="高",
        field=f"rf.{table}.{field}",
        message=message,
        evidence=json.dumps({"working_order_code": "WO-SPLIT", "rf_table": table, **evidence}, ensure_ascii=False),
    )


@pytest.mark.parametrize(
    ("rule_id", "table", "field", "message", "evidence", "form"),
    [
        (
            "RF_RANGE_VALUE_MISSING",
            "RF_W_GASEOUSCHECK_NOX",
            "PMTCHECKVALUE",
            "参考PMT信号检查值未填",
            {},
            {"REMARK": ""},
        ),
        (
            "RF_PM_TEMP_ERROR_OUT_OF_RANGE",
            "RF_Q_PMPRESSURE",
            "PM25CHECKTEMP3VALUE",
            "颗粒物温度误差超出±2℃",
            {
                "violations": [
                    {
                        "field": "PM25CHECKTEMP3VALUE",
                        "calibration_situation_field": "PM25CHECKTEMP4VALUE",
                        "calibration_situation": "仅作参考",
                    }
                ]
            },
            {"PM25CHECKTEMP4VALUE": "仅作参考"},
        ),
        (
            "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT",
            "RF_HY_EnvironmentHumidity",
            "CailbPrevReadNum/CailbNextReadNum",
            "环境湿度校准前后读数完全一致",
            {"remark_candidates": {"REMARK": "已核对"}},
            {"REMARK": "已核对"},
        ),
    ],
)
def test_existing_abnormal_fact_rules_get_linked_explanation_review(
    rule_id, table, field, message, evidence, form
):
    base = _base_issue(rule_id, table, field, message, evidence)
    issues = [base]

    check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-SPLIT"},
        [(table, {"WORKINGORDERCODE": "WO-SPLIT", **form})],
        issues,
    )

    companions = [issue for issue in issues if issue.rule_id == "RF_ABNORMAL_VALUE_NO_REMARK"]
    assert len(companions) == 1
    base_link = issue_link_metadata(asdict(base), working_order_code="WO-SPLIT")
    companion_link = issue_link_metadata(asdict(companions[0]), working_order_code="WO-SPLIT")
    assert base_link["issue_group_id"] == companion_link["issue_group_id"]
    assert companion_link["linked_rule_id"] == rule_id


def test_process_type_metadata_does_not_count_as_an_abnormal_remark():
    base = _base_issue(
        "RF_RANGE_OUT_OF_SPEC",
        "RF_W_GASEOUSCHECK_NOX",
        "GYCHECKVALUE",
        "高压电源超出范围",
        {"handling_record_candidates": {"GYCHECKROW": "", "PROCESSTYPE": 1.0}},
    )
    issues = [base]

    check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-SPLIT"},
        [
            (
                "RF_W_GASEOUSCHECK_NOX",
                {"WORKINGORDERCODE": "WO-SPLIT", "REMARK": "", "GYCHECKROW": "", "PROCESSTYPE": 1.0},
            )
        ],
        issues,
    )

    companion = next(issue for issue in issues if issue.rule_id == "RF_ABNORMAL_VALUE_NO_REMARK")
    evidence = json.loads(companion.evidence)
    assert evidence["remark_candidates"] == {"REMARK": "", "GYCHECKROW": ""}
    assert evidence["needs_semantic_review"] is False
    assert "未填写有效备注" in companion.message


def test_pm_sample_tube_temperature_emits_fact_and_explanation_review():
    issues = []
    check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-PM-TEMP"},
        [
            (
                "RF_W_PMCHECK",
                {
                    "WORKINGORDERCODE": "WO-PM-TEMP",
                    "AIRTEMPVALUE": "/",
                    "AIRTEMPISNORMAL": "否",
                    "AIRTEMPEXCEPTION": "等待配件",
                },
            )
        ],
        issues,
    )

    assert [issue.rule_id for issue in issues] == [
        "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL",
        "RF_ABNORMAL_VALUE_NO_REMARK",
    ]
    companion_evidence = json.loads(issues[1].evidence)
    assert companion_evidence["reason_rule_id"] == "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL"
    assert companion_evidence["remark_candidates"]["AIRTEMPEXCEPTION"] == "等待配件"


def test_abnormal_result_field_emits_fact_even_when_field_contains_context():
    issues = []
    check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-RESULT"},
        [
            (
                "RF_W_OTHERDEVICECHECK",
                {
                    "WORKINGORDERCODE": "WO-RESULT",
                    "WEATHERDEVICEMODEL": "WS-1",
                    "WEATHERSITUATION": "气象仪故障通讯失败，已处理并返厂维修",
                },
            )
        ],
        issues,
    )

    assert [issue.rule_id for issue in issues] == [
        "RF_ABNORMAL_RESULT_FIELD",
        "RF_ABNORMAL_VALUE_NO_REMARK",
    ]
    companion_evidence = json.loads(issues[1].evidence)
    assert companion_evidence["remark_candidates"]["WEATHERSITUATION"] == "气象仪故障通讯失败，已处理并返厂维修"
