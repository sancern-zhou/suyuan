"""Shared project-root resolution for utility tools."""

from pathlib import Path

from app.utils.path_config import PROJECT_ROOT


def get_project_root() -> Path:
    """Return the project root directory (suyuan).

    The value comes from the centralized path contract and does not depend on
    the process working directory or this module's nesting depth.
    """
    return PROJECT_ROOT
