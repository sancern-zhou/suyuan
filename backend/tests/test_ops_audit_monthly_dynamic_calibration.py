import json

import pytest

from app.services.ops_audit.rules.workflow_rules import check_workflow_completeness
from app.services.ops_work_order_audit_engine import audit_dataset


RULE_ID = "WO_MONTHLY_DYNAMIC_CALIBRATION_DURATION_TOO_SHORT"


def _order(**overrides):
    return {
        "WORKINGORDERCODE": "WO-DYNAMIC-1",
        "DDWORKINGORDERTYPE": "Check",
        "MAINTENANCETYPE": "Month",
        "ORDERTITLE": "动态校准仪流量校准检查",
        **overrides,
    }


def _details(end_time):
    return [
        {"PROCESSSTEP": "CreateOrder", "PROCESSSTARTDATETIME": "2026-06-08 09:00:00"},
        {
            "PROCESSSTEP": "CheckOrder",
            "PROCESSSTARTDATETIME": "2026-06-08 10:00:00",
            "PROCESSENDDATETIME": end_time,
        },
    ]


@pytest.mark.parametrize(
    ("end_time", "expected_issue"),
    [
        ("2026-06-08 10:04:59", True),
        ("2026-06-08 10:05:00", True),
        ("2026-06-08 10:05:01", False),
        ("2026-06-08 09:59:00", True),
        (None, False),
    ],
)
def test_monthly_dynamic_calibration_requires_more_than_five_minutes(end_time, expected_issue):
    issues = []

    check_workflow_completeness(_order(), _details(end_time), issues)

    matched = [issue for issue in issues if issue.rule_id == RULE_ID]
    assert bool(matched) is expected_issue
    if end_time == "2026-06-08 10:05:00":
        assert json.loads(matched[0].evidence)["duration_minutes"] == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"MAINTENANCETYPE": "Quarter"},
        {"DDWORKINGORDERTYPE": "Fault"},
        {"ORDERTITLE": "月度气态分析仪校准检查"},
    ],
)
def test_monthly_dynamic_calibration_rule_ignores_other_orders(overrides):
    issues = []

    check_workflow_completeness(_order(**overrides), _details("2026-06-08 10:01:00"), issues)

    assert RULE_ID not in {issue.rule_id for issue in issues}


def test_monthly_dynamic_calibration_rule_only_checks_processing_steps():
    issues = []
    details = _details("2026-06-08 10:06:00") + [
        {
            "PROCESSSTEP": "Review",
            "PROCESSSTARTDATETIME": "2026-06-08 10:07:00",
            "PROCESSENDDATETIME": "2026-06-08 10:08:00",
        }
    ]

    check_workflow_completeness(_order(), details, issues)

    assert RULE_ID not in {issue.rule_id for issue in issues}


def test_monthly_dynamic_calibration_issue_reaches_audit_results():
    order = _order()
    dataset = {
        "orders": [order],
        "details": [
            {"WORKINGORDERCODE": order["WORKINGORDERCODE"], **detail}
            for detail in _details("2026-06-08 10:05:00")
        ],
        "rf_forms": {},
        "attachments": [],
        "wo_commonfile": [],
        "devices": [],
    }

    audit = audit_dataset(dataset, enable_visual=False)

    assert RULE_ID in {issue["rule_id"] for issue in audit["records"][0]["deterministic_issues"]}
