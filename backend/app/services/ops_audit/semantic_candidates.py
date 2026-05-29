"""Semantic review candidate generation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.ops_audit.config import rules_for_review_stage

SEMANTIC_RULE_IDS = rules_for_review_stage("semantic_remark")


def build_semantic_candidates(audit: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for record in audit["records"]:
        matched_issues = [issue for issue in record.get("scoring_issues", []) if issue.get("rule_id") in SEMANTIC_RULE_IDS]
        if not matched_issues:
            continue
        candidates.append(
            {
                "working_order_code": record["working_order_code"],
                "station_id": record["station_id"],
                "order_type": record["order_type"],
                "maintenance_type": record["maintenance_type"],
                "finish_time": record["finish_time"],
                "classification": record["audit_level"],
                "deterministic_issue_count": record.get("deterministic_issue_count", 0),
                "candidate_issue_count": record.get("candidate_issue_count", 0),
                "workflow_steps": record["workflow_steps"],
                "rf_tables": record["rf_tables"],
                "attachment_count": record.get("attachment_count", 0),
                "attachment_review_rules": record.get("attachment_review_rules", []),
                "semantic_focus": sorted({issue["rule_id"] for issue in matched_issues}),
                "evidence_issues": matched_issues[:12],
            }
        )
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "input_candidates_for_remark_closure_semantic_review",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
