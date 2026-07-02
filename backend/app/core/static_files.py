"""Static file mounting extracted from app/main.py."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import structlog

logger = structlog.get_logger()


def get_frontend_dist_path() -> Path | None:
    """Return the built frontend directory when available."""
    dist_path = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    index_path = dist_path / "index.html"
    if dist_path.exists() and index_path.exists():
        return dist_path
    return None


def mount_static_files(app: FastAPI) -> None:
    """Mount static assets if the backend static directory exists."""
    static_path = Path(__file__).resolve().parents[2] / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info("static_files_mounted", path=str(static_path))

    frontend_dist = get_frontend_dist_path()
    if frontend_dist:
        for directory_name in ("assets", "reports", "dist"):
            directory = frontend_dist / directory_name
            if directory.exists():
                app.mount(
                    f"/{directory_name}",
                    StaticFiles(directory=str(directory)),
                    name=f"frontend_{directory_name}",
                )
        logger.info("frontend_static_files_mounted", path=str(frontend_dist))
