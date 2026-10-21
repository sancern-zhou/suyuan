"""Detect event-loop stalls by measuring asyncio.sleep overshoot."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger()

_watchdog_task: asyncio.Task | None = None


async def _watchdog_loop(interval_seconds: float, threshold_seconds: float) -> None:
    loop = asyncio.get_running_loop()
    logger.info(
        "loop_watchdog_started",
        interval_seconds=interval_seconds,
        threshold_seconds=threshold_seconds,
    )
    while True:
        started = loop.time()
        await asyncio.sleep(interval_seconds)
        lag_seconds = loop.time() - started - interval_seconds
        if lag_seconds >= threshold_seconds:
            logger.warning(
                "event_loop_lag",
                lag_ms=round(lag_seconds * 1000),
                interval_seconds=interval_seconds,
            )


def start_loop_watchdog(
    *,
    interval_seconds: float = 1.0,
    threshold_seconds: float = 1.0,
) -> asyncio.Task:
    """Start the watchdog task; safe to call multiple times."""
    global _watchdog_task
    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = asyncio.create_task(
            _watchdog_loop(interval_seconds, threshold_seconds)
        )
    return _watchdog_task


async def stop_loop_watchdog() -> None:
    global _watchdog_task
    task = _watchdog_task
    _watchdog_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
