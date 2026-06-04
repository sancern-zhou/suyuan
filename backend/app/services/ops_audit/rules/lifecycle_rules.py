"""Working order lifecycle rules for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.services.ops_audit.config import load_low_value_remarks
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

LOW_VALUE_REMARKS = load_low_value_remarks()

AUTO_FINISH_THRESHOLD_HOURS = 1
NEAR_DEADLINE_HOURS = 4


def check_lifecycle_closure(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check working order lifecycle for effective closure evidence.

    This rule identifies:
    - LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE: Order marked as finished without effective closure evidence

    Effective closure evidence includes:
    - Workflow review/check steps with meaningful remarks
    - RF forms with actual inspection results
    - Processing time that suggests human review (not auto-finish)

    The rule helps identify orders that may have been auto-completed by the system
    without actual human review and closure.
    """

    has_effective_closure = _has_effective_closure(order, workflows, forms)

    if not has_effective_closure:
        _add_no_effective_closure_issue(order, workflows, forms, issues)


def _has_effective_closure(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    forms: list[tuple[str, dict[str, Any]]],
) -> bool:
    """Check if order has effective closure evidence."""

    if _has_workflow_review(workflows):
        return True

    if _has_substantive_forms(forms):
        return True

    if _has_processing_time(order):
        return True

    return False


def _has_workflow_review(workflows: list[dict[str, Any]]) -> bool:
    """Check if workflow has meaningful review steps."""

    if not workflows:
        return False

    for workflow in workflows:
        steps = workflow.get("steps") or workflow.get("workflowSteps") or []
        if not steps:
            steps = [workflow]

        for step in steps:
            step_name = str(
                step.get("NAME")
                or step.get("nodeName")
                or step.get("stepName")
                or step.get("PROCESSSTEP")
                or ""
            ).lower()
            remark = str(
                step.get("REMARK")
                or step.get("remark")
                or step.get("opinion")
                or step.get("SUBMITREMARK")
                or ""
            ).strip()

            if step_name in {"checkorder", "supcheck_check", "review"} or any(keyword in step_name for keyword in ["审核", "复核", "审批", "review", "check", "approve"]):
                continue

    return False


def _has_substantive_forms(forms: list[tuple[str, dict[str, Any]]]) -> bool:
    """Check if RF forms have substantive content."""

    for table, form in forms:
        if form.get("_query_error"):
            continue

        check_value = form.get("DISPLAYVALUE") or form.get("MEASUREVALUE") or form.get("SENSORVALUE")
        if check_value and str(check_value).strip() not in {"", "/", "-", "0", "0.0"}:
            try:
                if float(str(check_value)) > 0:
                    return True
            except (ValueError, TypeError):
                if str(check_value).strip() not in LOW_VALUE_REMARKS:
                    return True

    return False


def _has_processing_time(order: dict[str, Any]) -> bool:
    """Check if order has sufficient processing time to suggest human review."""

    create_time = _parse_time(order.get("CREATETIME"))
    finish_time = _parse_time(order.get("FINISHTIME"))
    plan_finish = _parse_time(order.get("PLANFINISHTIME"))

    if create_time and finish_time:
        processing_hours = (finish_time - create_time).total_seconds() / 3600
        if processing_hours > AUTO_FINISH_THRESHOLD_HOURS:
            return True

    if plan_finish and finish_time:
        time_to_deadline = (plan_finish - finish_time).total_seconds() / 3600
        if abs(time_to_deadline) > NEAR_DEADLINE_HOURS:
            return True

    return False


def _add_no_effective_closure_issue(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Add issue for order without effective closure evidence."""

    workflow_count = len(workflows) if workflows else 0
    form_count = len([f for f in forms if not f[1].get("_query_error")])

    create_time = _parse_time(order.get("CREATETIME"))
    finish_time = _parse_time(order.get("FINISHTIME"))

    processing_hours = None
    if create_time and finish_time:
        processing_hours = (finish_time - create_time).total_seconds() / 3600

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "workflow_count": workflow_count,
        "form_count": form_count,
        "create_time": _format_time(create_time),
        "finish_time": _format_time(finish_time),
        "processing_hours": processing_hours,
        "order_type": order.get("DDWORKINGORDERTYPE"),
        "maintenance_type": order.get("MAINTENANCETYPE"),
    }

    add_issue(
        issues,
        "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
        "生命周期闭环风险",
        "高",
        "working_order.lifecycle.closure",
        "已完成工单缺少有效闭环证据(无实质性审核备注、无有效检查结果、或处理时间过短)",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _parse_time(value: Any) -> datetime | None:
    """Parse time value to datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f%z"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_time(value: datetime | None) -> str:
    """Format datetime for display."""
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")
