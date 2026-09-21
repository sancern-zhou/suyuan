"""Bootstrap project task definitions without overwriting runtime configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import PROJECT_ROOT

from .models import ScheduledTask

logger = structlog.get_logger()


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
        else:
            action = "unchanged"
        results.append({"task_id": task_id, "action": action, "path": str(path)})
        logger.info("project_scheduled_task_synced", task_id=task_id, action=action)
    return results
