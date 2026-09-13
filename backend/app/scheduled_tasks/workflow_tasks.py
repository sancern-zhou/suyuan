"""Deterministic scheduled-workflow runners.

Workflow tasks deliberately bypass the Agent.  A handler owns both the fixed
workflow invocation and any deterministic human-review hand-off required by
the task, so a successful execution always represents a business outcome.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.services.task_review import submit_review
from app.scheduled_tasks.models import ScheduledTask
from app.scheduled_tasks.models.execution import TaskExecution


async def _run_network_inspection(task: ScheduledTask, execution: TaskExecution) -> dict[str, Any]:
    from app.tools.workflow.jiangsu_network_inspection_workflow import JiangsuNetworkInspectionWorkflow

    args = dict(task.workflow_args)
    result = await JiangsuNetworkInspectionWorkflow().execute(**args)
    if not result.get("success"):
        raise RuntimeError(result.get("summary") or "网络巡检工作流执行失败")

    data = result.get("data") or {}
    conclusion = str(data.get("conclusion") or result.get("summary") or "").strip()
    issues = data.get("issues")
    if not conclusion or not isinstance(issues, list):
        raise RuntimeError("网络巡检工作流未返回有效 conclusion/issues")
    if not 200 <= len(conclusion) <= 300:
        raise RuntimeError(f"网络巡检结论长度不符合要求：{len(conclusion)} 字")

    issue_lines = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_lines.append(
            f"{issue.get('city') or '未知城市'} / {issue.get('station_name') or '未命名站点'}"
            f"（{issue.get('category') or '巡检异常'}）"
        )
    subject_id = f"网络巡检-{datetime.now().astimezone().date().isoformat()}"
    payload = {
        "subject_id": subject_id,
        "category": "运维值守",
        "title": "江苏全网巡检值守",
        "summary": conclusion,
        "decision": "needs_action" if issues else "approve",
        "comment": conclusion + "\n问题清单：" + ("；".join(issue_lines) if issue_lines else "无异常问题"),
        "checks": [
            {"name": "巡检覆盖", "status": "pass", "basis": f"实际覆盖 {data.get('station_count', 0)} 个站点"},
            {"name": "异常站点", "status": "fail" if issues else "pass", "basis": f"发现 {len(issues)} 个异常站点"},
            {"name": "数据完整性", "status": "pass", "basis": "接口返回站点清单和异常明细"},
        ],
        "sections": [
            {"title": "巡检统计", "fields": [
                {"key": "station_count", "label": "覆盖站点", "value": str(data.get("station_count", 0))},
                {"key": "alarm_station_count", "label": "异常站点", "value": str(data.get("alarm_station_count", 0))},
                {"key": "alarm_city_count", "label": "异常城市", "value": str(data.get("alarm_city_count", 0))},
            ]}
        ],
        "evidence": [],
    }
    source = {
        "task_id": task.task_id,
        "task_name": task.name,
        "execution_id": execution.execution_id,
        "allow_archived_review_reopen": task.allow_archived_review_reopen,
        "result_requirements": [rule.model_dump(mode="json") for rule in task.result_requirements],
    }
    review = await asyncio.to_thread(submit_review, payload, source)
    return {
        "summary": conclusion,
        "review_id": review["review_id"],
        "data": data,
        "workflow_result": result,
    }


_WORKFLOW_HANDLERS = {
    "jiangsu_network_inspection_workflow": _run_network_inspection,
}


async def execute_workflow_task(task: ScheduledTask, execution: TaskExecution) -> dict[str, Any]:
    if not task.workflow_name:
        raise RuntimeError("workflow task 未配置 workflow_name")
    handler = _WORKFLOW_HANDLERS.get(task.workflow_name)
    if handler is None:
        raise RuntimeError(f"未注册的 workflow：{task.workflow_name}")
    return await handler(task, execution)
