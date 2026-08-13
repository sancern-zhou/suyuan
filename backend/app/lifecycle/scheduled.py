"""Scheduled task lifecycle extracted from app/main.py.

Dependency note:
- The scheduled task service receives an Agent factory.
- Start it after LLM tools have been initialized so task-created Agents see the
  current tool registry.
"""

import structlog

logger = structlog.get_logger()


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

        service = init_service(agent_factory=lambda **kwargs: create_react_agent(**kwargs))
        from app.scheduled_tasks.default_tasks import ensure_project_default_tasks

        created = ensure_project_default_tasks(service, context.manifest.scheduled_tasks)
        start_service()
        logger.info("scheduled_task_service_started", default_tasks_created=created)
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
