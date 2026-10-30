"""Operation-access roster lifecycle: keep the snapshot fresh in both roles.

Web and worker each run the refresh loop so the whitelist survives one of
them being down; the snapshot file under the data registry is the shared
fallback across restarts.
"""

from __future__ import annotations

import asyncio

import structlog

from config.settings import settings

logger = structlog.get_logger()


async def start_operation_access_policy(app) -> None:
    if settings.auth_mode != "operation":
        return
    if not settings.auth_operation_access_control_enabled:
        logger.info("operation_access_control_disabled")
        return

    from app.auth.operation_access import OperationAccessPolicy

    policy = getattr(app.state, "operation_access_policy", None)
    if policy is None:
        policy = OperationAccessPolicy(settings=settings)
        app.state.operation_access_policy = policy

    # Refresh once inline so the whitelist is populated before the app
    # accepts traffic; a failure here still fails open until the loop retries.
    await policy.refresh()

    stop_event = asyncio.Event()
    app.state.operation_access_policy_stop = stop_event
    app.state.operation_access_policy_task = asyncio.create_task(
        policy.run_forever(stop_event)
    )
    logger.info("operation_access_policy_started")


async def stop_operation_access_policy(app) -> None:
    task = getattr(app.state, "operation_access_policy_task", None)
    if task is None:
        return
    stop_event = getattr(app.state, "operation_access_policy_stop", None)
    if stop_event is not None:
        stop_event.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    app.state.operation_access_policy_task = None
    logger.info("operation_access_policy_stopped")
