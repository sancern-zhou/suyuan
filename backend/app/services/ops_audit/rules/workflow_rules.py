"""Working order workflow rules for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


def check_workflow_completeness(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Check working order workflow for completeness.

    This rule identifies:
    - FLOW_MISSING: Workflow is missing
    - FLOW_NO_CREATE: Workflow has no create step
    - FLOW_NO_CHECK: Workflow has no review/check step

    These rules ensure proper workflow documentation for audit trails.
    """

    if not workflows:
        _add_flow_missing_issue(order, issues)
        return

    _check_monthly_dynamic_calibration_duration(order, workflows, issues)

    if any("PROCESSSTEP" in workflow for workflow in workflows):
        _check_flow_steps(order, {"steps": workflows}, issues)
        return

    for workflow in workflows:
        _check_flow_steps(order, workflow, issues)


def _check_monthly_dynamic_calibration_duration(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    title = str(order.get("ORDERTITLE") or "")
    if (
        order.get("DDWORKINGORDERTYPE") != "Check"
        or order.get("MAINTENANCETYPE") != "Month"
        or "动态" not in title
        or "校准" not in title
    ):
        return

    for workflow in workflows:
        steps = workflow.get("steps") or workflow.get("workflowSteps") or [workflow]
        for step in steps:
            if step.get("PROCESSSTEP") != "CheckOrder":
                continue
            start = _parse_workflow_time(step.get("PROCESSSTARTDATETIME"))
            end = _parse_workflow_time(step.get("PROCESSENDDATETIME"))
            if not start or not end:
                continue
            duration_minutes = (end - start).total_seconds() / 60
            if duration_minutes > 5:
                continue

            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "order_title": title,
                "process_step": "CheckOrder",
                "start_time": start.isoformat(sep=" "),
                "end_time": end.isoformat(sep=" "),
                "duration_minutes": round(duration_minutes, 2),
                "required_minutes_exclusive": 5,
            }
            add_issue(
                issues,
                "WO_MONTHLY_DYNAMIC_CALIBRATION_DURATION_TOO_SHORT",
                "时间合理性",
                "高",
                "working_order_details.PROCESSSTARTDATETIME/PROCESSENDDATETIME",
                f"月度动态校准维护处理时长{duration_minutes:.2f}分钟，未超过5分钟",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )


def _parse_workflow_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _add_flow_missing_issue(
    order: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Add issue for missing workflow."""

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "workflow_count": 0,
        "order_status": order.get("STATUS"),
    }

    add_issue(
        issues,
        "FLOW_MISSING",
        "流程完整性",
        "高",
        "working_order.workflow",
        "工单流程缺失",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_flow_steps(
    order: dict[str, Any],
    workflow: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check workflow for required steps."""

    steps = workflow.get("steps") or workflow.get("workflowSteps") or []
    if not steps:
        steps = [workflow]

    has_create = False
    has_check = False
    has_review = False

    step_details = []
    for step in steps:
        raw_step_name = (
            step.get("NAME")
            or step.get("nodeName")
            or step.get("stepName")
            or step.get("PROCESSSTEP")
            or ""
        )
        step_name = str(raw_step_name).lower()
        step_type = str(step.get("TYPE") or step.get("nodeType") or step.get("PROCESSSTEP") or "").lower()

        step_details.append({
            "name": raw_step_name,
            "type": step.get("TYPE") or step.get("nodeType"),
            "create_time": step.get("CREATETIME") or step.get("createTime") or step.get("PROCESSSTARTDATETIME"),
        })

        if step_name == "createorder" or any(keyword in step_name for keyword in ["创建", "提交", "申请", "新建", "create", "submit"]):
            has_create = True
        if step_name in {"checkorder", "supcheck_check", "review"} or any(keyword in step_name for keyword in ["审核", "复核", "审批", "检查", "review", "check", "approve"]):
            has_check = True
        if "review" in step_type or "审批" in step_name:
            has_review = True

    if not has_create:
        _add_no_create_issue(order, workflow, step_details, issues)

    if not has_check and not has_review:
        _add_no_check_issue(order, workflow, step_details, issues)


def _add_no_create_issue(
    order: dict[str, Any],
    workflow: dict[str, Any],
    step_details: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Add issue for workflow without create step."""

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "workflow_id": workflow.get("WORKFLOWID") or workflow.get("workflowId"),
        "step_count": len(step_details),
        "steps": step_details[:5],
    }

    add_issue(
        issues,
        "FLOW_NO_CREATE",
        "流程完整性",
        "中",
        "working_order.workflow.create",
        "工单流程无创建步骤",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_no_check_issue(
    order: dict[str, Any],
    workflow: dict[str, Any],
    step_details: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Add issue for workflow without check/review step."""

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "workflow_id": workflow.get("WORKFLOWID") or workflow.get("workflowId"),
        "step_count": len(step_details),
        "steps": step_details[:5],
    }

    add_issue(
        issues,
        "FLOW_NO_CHECK",
        "流程完整性",
        "高",
        "working_order.workflow.check",
        "工单流程无审核步骤",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )
