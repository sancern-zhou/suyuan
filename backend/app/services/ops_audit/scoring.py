"""Rule classification for ops audits."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.services.ops_audit.config import load_scoring_config, review_stage_for_rule
from app.services.ops_audit.models import Issue

_SCORING = load_scoring_config()
SEVERITY_PENALTY = _SCORING["severity_penalty"]
COMMON_PATTERN_ELIGIBLE_RULES = set(_SCORING["common_pattern_eligible_rules"])
HARD_ERROR_RULES = set(_SCORING["hard_error_rules"])
CRITICAL_HARD_ERROR_RULES = set(_SCORING["critical_hard_error_rules"])
COMMON_PATTERN_MIN_AFFECTED_ORDERS = int(_SCORING["common_pattern_min_affected_orders"])
COMMON_PATTERN_ORDER_RATIO = float(_SCORING["common_pattern_order_ratio"])


def severity_score(issues: list[Issue] | list[dict[str, Any]]) -> int | None:
    """Deprecated compatibility shim. Ops audits no longer use numeric scores."""

    return None


def risk_level(score: int | None, issues: list[Issue] | list[dict[str, Any]]) -> str:
    """Return the only user-facing classification used by ops audits."""

    issue_rule_ids = {
        issue.rule_id if isinstance(issue, Issue) else issue.get("rule_id")
        for issue in issues
    }
    return "有问题" if issue_rule_ids else ""


def classify_rule_patterns(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    order_count = max(len(records), 1)
    raw_counter = Counter()
    affected_orders: dict[str, set[str]] = defaultdict(set)
    severity_by_rule: dict[str, Counter] = defaultdict(Counter)
    category_by_rule: dict[str, Counter] = defaultdict(Counter)
    order_type_by_rule: dict[str, Counter] = defaultdict(Counter)

    for record in records:
        code = record.get("working_order_code")
        for issue in record.get("issues", []):
            rule_id = issue.get("rule_id")
            raw_counter[rule_id] += 1
            affected_orders[rule_id].add(code)
            severity_by_rule[rule_id][issue.get("severity")] += 1
            category_by_rule[rule_id][issue.get("category")] += 1
            order_type_by_rule[rule_id][record.get("order_type") or "<空>"] += 1

    patterns: dict[str, dict[str, Any]] = {}
    for rule_id, raw_hit_count in raw_counter.items():
        affected_count = len(affected_orders[rule_id])
        affected_ratio = affected_count / order_count
        eligible = False
        if rule_id in HARD_ERROR_RULES:
            pattern_type = "deterministic_issue"
            recommendation = "该规则属于硬性结构/逻辑问题，可作为确定性问题处理。"
        else:
            pattern_type = "candidate_issue"
            recommendation = "该规则为待确认问题，可结合样例、RF表、附件和语义审核进一步判断。"

        patterns[rule_id] = {
            "rule_id": rule_id,
            "raw_hit_count": raw_hit_count,
            "affected_order_count": affected_count,
            "affected_order_ratio": round(affected_ratio, 4),
            "pattern_type": pattern_type,
            "eligible_for_common_pattern": eligible,
            "dominant_severity": severity_by_rule[rule_id].most_common(1)[0][0],
            "dominant_category": category_by_rule[rule_id].most_common(1)[0][0],
            "order_type_counts": dict(order_type_by_rule[rule_id]),
            "recommendation": recommendation,
        }
    return patterns


def apply_rule_pattern_assessment(records: list[dict[str, Any]], rule_patterns: dict[str, dict[str, Any]]) -> None:
    for record in records:
        deterministic_issues = []
        candidate_issues = []
        deterministic_rules = []
        candidate_rules = []
        technical_diagnostics = []

        for issue in record.get("issues", []):
            if review_stage_for_rule(issue.get("rule_id")) == "technical_diagnostic":
                issue["pattern_type"] = "technical_diagnostic"
                issue["assessment"] = "technical_diagnostic"
                technical_diagnostics.append(issue)
                continue
            pattern = rule_patterns.get(issue.get("rule_id"), {})
            pattern_type = pattern.get("pattern_type", "candidate_issue")
            if _requires_semantic_assessment(issue):
                pattern_type = "candidate_issue"
            issue["pattern_type"] = pattern_type
            if pattern_type == "deterministic_issue":
                issue["assessment"] = "deterministic_issue"
                deterministic_rules.append(issue.get("rule_id"))
                deterministic_issues.append(issue)
            else:
                issue["assessment"] = "candidate_issue"
                candidate_rules.append(issue.get("rule_id"))
                candidate_issues.append(issue)

        record["score"] = None
        record["audit_level"] = risk_level(None, deterministic_issues or candidate_issues)
        record["scoring_issue_count"] = len(deterministic_issues) + len(candidate_issues)
        record["scoring_issues"] = deterministic_issues + candidate_issues
        record["deterministic_issue_count"] = len(deterministic_issues)
        record["candidate_issue_count"] = len(candidate_issues)
        record["deterministic_issues"] = deterministic_issues
        record["candidate_issues"] = candidate_issues
        record["technical_diagnostics"] = technical_diagnostics
        record["technical_diagnostic_count"] = len(technical_diagnostics)
        record["common_pattern_rules"] = []
        record["candidate_rules"] = sorted(set(candidate_rules))
        record["deterministic_rules"] = sorted(set(deterministic_rules))


def _requires_semantic_assessment(issue: dict[str, Any]) -> bool:
    evidence = issue.get("evidence")
    if not isinstance(evidence, str):
        return False
    return '"needs_semantic_review": true' in evidence or '"needs_semantic_review":true' in evidence
