"""Shared project-root resolution for utility tools."""

from pathlib import Path


def get_project_root() -> Path:
    """Return the project root directory (suyuan).

    This module lives at app/tools/utility/project_root.py, so parents[4]
    resolves to the suyuan directory (parent of backend).
    """
    return Path(__file__).resolve().parents[4]
