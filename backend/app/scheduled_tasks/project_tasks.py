"""Bootstrap project task definitions without overwriting user configuration."""

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
    """Create missing tasks; the persistent runtime store is the source of truth."""
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
        else:
            action = "unchanged"
        results.append({"task_id": task_id, "action": action, "path": str(path)})
        logger.info("project_scheduled_task_synced", task_id=task_id, action=action)
    return results
