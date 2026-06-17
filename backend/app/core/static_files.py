"""Static file mounting extracted from app/main.py."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import structlog

logger = structlog.get_logger()


def mount_static_files(app: FastAPI) -> None:
    """Mount static assets if the backend static directory exists."""
    static_path = Path(__file__).resolve().parents[2] / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info("static_files_mounted", path=str(static_path))

