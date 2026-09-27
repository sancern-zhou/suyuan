"""Upgrade only the original seeded weather task to its evidence contract."""

from __future__ import annotations

import structlog

from app.scheduled_tasks.models import ScheduledTask
from app.utils.path_config import PROJECT_ROOT

logger = structlog.get_logger()
TASK_ID = "task_xuchang_weekly_weather_situation_report"
OLD_PROMPT_MARKER = "使用 execute_sql_query 按 skill 查询前7天 NMC 气象预报"


def migrate_weather_task(service) -> bool:
    """Existing persisted tasks are authoritative; upgrade only the known seed."""
    current = service.task_storage.get(TASK_ID)
    if current is None or current.event_type == "xuchang.weather_situation.evidence_ready":
        return False
    if OLD_PROMPT_MARKER not in current.prompt:
        logger.warning("xuchang_weather_task_customized_skip_migration", task_id=TASK_ID)
        return False
    seed_path = PROJECT_ROOT / "projects" / "xuchang" / "scheduled_tasks" / f"{TASK_ID}.json"
    seed = ScheduledTask.model_validate_json(seed_path.read_text(encoding="utf-8"))
    data = current.model_dump()
    for field in ("description", "tool_names", "trigger_type", "schedule_type",
                  "event_type", "event_filters", "prompt", "history_learning",
                  "timeout_seconds", "skill_id"):
        data[field] = getattr(seed, field)
    service.update_task(ScheduledTask.model_validate(data))
    logger.info("xuchang_weather_task_migrated_to_evidence", task_id=TASK_ID)
    return True
