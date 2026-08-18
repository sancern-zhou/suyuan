"""Single-process background worker entrypoint.

Run with:
    python -m app.worker [--env-file .env.customer]
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace


def _requested_env_file(argv: list[str]) -> Path:
    try:
        index = argv.index("--env-file")
    except ValueError:
        return Path(".env").resolve()
    if index + 1 >= len(argv):
        raise SystemExit("--env-file requires a path")
    return Path(argv[index + 1]).expanduser().resolve()


def _load_requested_env_file(argv: list[str]) -> None:
    """Load deployment overrides before application settings are imported."""
    if "--env-file" not in argv:
        return
    from dotenv import load_dotenv

    env_path = _requested_env_file(argv)
    if not env_path.is_file():
        raise SystemExit(f"environment file not found: {env_path}")
    load_dotenv(env_path, override=True)


def _validate_data_registry_config(argv: list[str]) -> None:
    from app.utils.deployment_preflight import (
        DeploymentConfigError,
        configured_data_registry,
    )

    try:
        registry = configured_data_registry(_requested_env_file(argv))
    except DeploymentConfigError as exc:
        raise SystemExit(f"invalid worker deployment config: {exc}") from exc
    print(f"[INFO] Data registry: {registry}")


_load_requested_env_file(sys.argv[1:])
if __name__ == "__main__":
    _validate_data_registry_config(sys.argv[1:])
# This entrypoint is always the single background worker.  A deployment env
# file may contain web defaults, but must not be allowed to disable scheduling.
os.environ["APP_ROLE"] = "worker"

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
