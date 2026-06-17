"""Base helpers shared by deterministic ops audit rules."""

from __future__ import annotations

from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rule_taxonomy import issue_category


def add_issue(
    issues: list[Issue],
    rule_id: str,
    category: str,
    severity: str,
    field: str,
    message: str,
    evidence: str,
) -> None:
    issues.append(Issue(rule_id, issue_category(rule_id, category), severity, field, message, evidence))
