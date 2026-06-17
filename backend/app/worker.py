"""Single-process background worker entrypoint.

Run with:
    APP_ROLE=worker python -m app.worker
"""

from __future__ import annotations

import asyncio
import os
import signal
from types import SimpleNamespace

os.environ.setdefault("APP_ROLE", "worker")

import structlog

from app.core.logging import configure_logging
from app.lifecycle.shutdown import run_shutdown
from app.lifecycle.startup import run_startup

configure_logging()
logger = structlog.get_logger()


async def main() -> None:
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    app = SimpleNamespace(state=SimpleNamespace())
    await run_startup(app)
    logger.info("background_worker_started")

    try:
        await stop_event.wait()
    finally:
        logger.info("background_worker_stopping")
        await run_shutdown(app)


if __name__ == "__main__":
    asyncio.run(main())
