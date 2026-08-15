"""Link value abnormalities with their independent remark assessments."""

from __future__ import annotations

import json
from typing import Any


VALUE_ABNORMAL_RULE_ID = "RF_RANGE_OUT_OF_SPEC"
ABNORMAL_WITHOUT_EXPLANATION_RULE_ID = "RF_ABNORMAL_VALUE_NO_REMARK"

ABNORMAL_FACT_COMPONENTS = {
    "RF_RANGE_OUT_OF_SPEC": "value_abnormal",
    "RF_RANGE_VALUE_MISSING": "value_missing",
    "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL": "abnormal_fact",
    "RF_ABNORMAL_RESULT_FIELD": "abnormal_fact",
    "RF_PM_TEMP_ERROR_OUT_OF_RANGE": "value_abnormal",
    "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT": "data_suspect",
}


def is_abnormal_fact_rule(rule_id: Any) -> bool:
    return str(rule_id or "") in ABNORMAL_FACT_COMPONENTS


def parse_issue_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def issue_link_metadata(
    issue: dict[str, Any],
    *,
    working_order_code: Any = None,
) -> dict[str, Any]:
    """Return stable component/link metadata for a split abnormal issue."""

    rule_id = str(issue.get("rule_id") or "")
    if rule_id not in {*ABNORMAL_FACT_COMPONENTS, ABNORMAL_WITHOUT_EXPLANATION_RULE_ID}:
        return {}

    evidence = parse_issue_evidence(issue.get("evidence"))
    code = str(working_order_code or evidence.get("working_order_code") or "").strip()
    rf_table = str(evidence.get("rf_table") or _rf_table_from_field(issue.get("field")) or "").strip()
    if rule_id in ABNORMAL_FACT_COMPONENTS:
        component = ABNORMAL_FACT_COMPONENTS[rule_id]
        anchor_field = str(issue.get("field") or evidence.get("field") or "").strip()
        linked_rule_id = ABNORMAL_WITHOUT_EXPLANATION_RULE_ID
    else:
        component = "abnormal_explanation_issue"
        anchor_field = str(evidence.get("abnormal_field") or issue.get("field") or "").strip()
        linked_rule_id = str(evidence.get("reason_rule_id") or VALUE_ABNORMAL_RULE_ID)

    group_parts = [code or "<unknown_order>", rf_table or "<unknown_table>", anchor_field or "<unknown_field>"]
    return {
        "issue_group_id": "::".join(group_parts),
        "issue_component": component,
        "linked_rule_id": linked_rule_id,
    }


def _rf_table_from_field(field: Any) -> str:
    parts = str(field or "").split(".")
    if len(parts) >= 2 and parts[0] in {"rf", "attachment"}:
        return parts[1]
    return ""
