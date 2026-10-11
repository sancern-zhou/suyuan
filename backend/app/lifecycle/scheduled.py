"""Scheduled task lifecycle extracted from app/main.py.

Dependency note:
- The scheduled task service receives an Agent factory.
- Start it after LLM tools have been initialized so task-created Agents see the
  current tool registry.
"""

import structlog

from typing import Any

logger = structlog.get_logger()


def register_project_workflow_handlers(project: str) -> None:
    """Workflow-mode task seeds run as deterministic code units.

    The owning project module registers its handlers here so both the web
    process (workflow listing/validation) and the worker process (execution)
    see the same registry before the scheduler starts.  Handlers must match
    the ``handler(task, execution, **kwargs)`` calling contract of
    ``execute_workflow_task``; scenario functions that expose keyword-only
    parameters get a thin positional adapter.
    """
    from app.scheduled_tasks.workflow_tasks import register_workflow_handler

    if project == "xuchang":
        from app.fetchers.xuchang_weather_situation import build_weather_evidence_event
        from app.scenarios.xuchang_weather_report.constants import EVENT_TYPE
        from app.scheduled_tasks.event_builders import register_manual_event_builder
        from app.scenarios.xuchang_station_deviation.alert_notification import (
            run_station_alert_workflow,
        )

        register_manual_event_builder(EVENT_TYPE, build_weather_evidence_event)

        async def run_xuchang_station_alert(
            task: Any,
            execution: Any,
            event: Any = None,
            history_section: str | None = None,
        ) -> dict[str, Any]:
            return await run_station_alert_workflow(
                task=task,
                execution=execution,
                event=event,
                history_section=history_section,
            )

        register_workflow_handler(
            "xuchang_station_deviation_alert", run_xuchang_station_alert
        )


async def start_scheduled_task_service() -> None:
    """Initialize and start scheduled task service."""
    try:
        from app.project_config.loader import load_project_context
        from config.settings import settings

        context = load_project_context(settings.project_id)
        if not context.manifest.scheduled_tasks_enabled:
            logger.info("scheduled_task_service_disabled_by_project", project=settings.project_id)
            return

        from app.agent.react_agent import create_react_agent
        from app.scheduled_tasks import init_service, start_service
        from app.scheduled_tasks.event_result_hooks import register_event_result_handler
        from app.services.jiangsu_smart_event import persist_scheduled_task_result

        # The callback is process-local, so register it in both web and worker
        # processes before event tasks can execute.
        register_event_result_handler(persist_scheduled_task_result)

        service = init_service(agent_factory=lambda **kwargs: create_react_agent(**kwargs))
        from app.scheduled_tasks.default_tasks import ensure_project_default_tasks
        from app.scheduled_tasks.project_tasks import sync_project_scheduled_tasks
        from app.utils.path_config import PROJECT_ROOT

        register_project_workflow_handlers(context.manifest.project)

        # JSON 种子（projects/<project>/scheduled_tasks/*.json）优先生效；
        # 其余任务仍由代码内默认任务工厂引导并随代码刷新。
        definition_root = PROJECT_ROOT / "projects" / context.manifest.project / "scheduled_tasks"
        json_seeded = {
            task_id for task_id in context.manifest.scheduled_tasks
            if (definition_root / f"{task_id}.json").is_file()
        }
        created = ensure_project_default_tasks(
            service, [tid for tid in context.manifest.scheduled_tasks if tid not in json_seeded]
        )
        synced = sync_project_scheduled_tasks(
            project_id=context.manifest.project,
            task_ids=[tid for tid in context.manifest.scheduled_tasks if tid in json_seeded],
            service=service,
        )
        if context.manifest.project == "xuchang":
            from app.scenarios.xuchang_weather_report.task_migration import migrate_weather_task
            migrate_weather_task(service)
        start_service()
        logger.info(
            "scheduled_task_service_started",
            default_tasks_created=created,
            project_tasks_synced=synced,
        )
    except Exception as e:
        logger.error("scheduled_task_service_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_scheduled_tasks")


async def stop_scheduled_task_service() -> None:
    """Stop scheduled task service."""
    try:
        from app.project_config.loader import load_project_context
        from config.settings import settings

        if not load_project_context(settings.project_id).manifest.scheduled_tasks_enabled:
            return

        from app.scheduled_tasks import stop_service_async

        await stop_service_async()
        logger.info("scheduled_task_service_stopped")
    except Exception as e:
        logger.warning("scheduled_task_service_stop_failed", error=str(e))
