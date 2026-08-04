"""Shared project-root resolution for utility tools."""

from pathlib import Path

from app.utils.path_config import PROJECT_ROOT


def get_project_root() -> Path:
    """Return the project root directory (suyuan).

    This module lives at app/tools/utility/project_root.py, so parents[4]
    resolves to the suyuan directory (parent of backend).
    """
    return PROJECT_ROOT
