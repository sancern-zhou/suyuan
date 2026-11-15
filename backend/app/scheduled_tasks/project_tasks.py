"""Bootstrap project task definitions without overwriting runtime configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import PROJECT_ROOT

from .models import ScheduledTask

logger = structlog.get_logger()

_MONITOR_TAG = "runtime-monitor"
# 监控任务中代码拥有的字段：种子变更需向已存在任务传播。
# enabled/调度/推送目标等运行时字段不在此列（部署侧可自主调整）。
_MONITOR_CODE_OWNED_FIELDS = (
    "name",
    "description",
    "prompt",
    "tool_names",
    "timeout_seconds",
    "tags",
    "history_learning",
)


def _monitor_definition_changed(definition: ScheduledTask, existing: ScheduledTask) -> bool:
    """监控任务（tags 含 runtime-monitor）的代码拥有字段是否与种子不一致。"""
    if _MONITOR_TAG not in (definition.tags or []):
        return False
    return any(
        getattr(definition, field) != getattr(existing, field)
        for field in _MONITOR_CODE_OWNED_FIELDS
    )


def sync_project_scheduled_tasks(
    *,
    project_id: str,
    task_ids: list[str],
    service: Any,
    project_root: Path = PROJECT_ROOT,
) -> list[dict[str, str]]:
    """Create missing tasks; the persistent runtime store is the source of truth.

    Existing tasks are never modified: configuration edited through the UI or
    API must survive restarts. Seed files only bootstrap tasks that do not
    exist yet; deploying a seed change requires explicitly updating or
    recreating the task.
    """
    results = []
    definition_root = project_root / "projects" / project_id / "scheduled_tasks"
    for task_id in task_ids:
        path = definition_root / f"{task_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"project scheduled task definition not found: {path}")
        definition = ScheduledTask.model_validate_json(path.read_text(encoding="utf-8"))
        if definition.task_id != task_id:
            raise ValueError(
                f"scheduled task id mismatch: manifest={task_id}, definition={definition.task_id}"
            )
        existing = service.task_storage.get(task_id)
        if existing is None:
            service.create_task(definition)
            action = "created"
        elif definition.execution_mode == "workflow" and existing.execution_mode != "workflow":
            # Workflow task definitions are deterministic code units.  When a
            # seeded task is upgraded from an Agent mode, migrate only the
            # execution contract and retain runtime-owned delivery/stat fields.
            task_data = existing.model_dump()
            task_data.update({
                "execution_mode": "workflow",
                "workflow_name": definition.workflow_name,
                "workflow_args": definition.workflow_args,
                "tool_names": None,
                "skill_id": None,
                "prompt": definition.prompt,
                "timeout_seconds": definition.timeout_seconds,
                "history_learning": definition.history_learning,
            })
            service.update_task(ScheduledTask.model_validate(task_data))
            action = "migrated_workflow"
        elif definition.execution_mode == "workflow" and existing.prompt != definition.prompt:
            # Workflow instructions are code-owned LLM guidance, so keep the
            # persisted task synchronized when the shared definition changes.
            task_data = existing.model_dump()
            task_data["prompt"] = definition.prompt
            task_data["timeout_seconds"] = definition.timeout_seconds
            service.update_task(ScheduledTask.model_validate(task_data))
            action = "updated_workflow_instruction"
        elif _monitor_definition_changed(definition, existing):
            # Runtime-monitor tasks are system-owned infrastructure (tagged
            # runtime-monitor): prompts/toolsets are code-owned and seeds must
            # propagate on redeploy.  Runtime-owned fields (enabled, schedule,
            # delivery targets) stay untouched.
            task_data = existing.model_dump()
            for field in (
                "name",
                "description",
                "prompt",
                "tool_names",
                "timeout_seconds",
                "tags",
                "history_learning",
            ):
                task_data[field] = getattr(definition, field)
            service.update_task(ScheduledTask.model_validate(task_data))
            action = "updated_monitor_definition"
        else:
            action = "unchanged"
        results.append({"task_id": task_id, "action": action, "path": str(path)})
        logger.info("project_scheduled_task_synced", task_id=task_id, action=action)
    return results
