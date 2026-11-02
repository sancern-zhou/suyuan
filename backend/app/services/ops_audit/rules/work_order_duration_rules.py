"""Working order processing-duration rules for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


def check_monthly_dynamic_calibration_duration(
    order: dict[str, Any],
    workflows: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Check that monthly dynamic calibration work takes more than five minutes."""

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
