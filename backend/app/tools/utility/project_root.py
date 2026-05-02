"""Shared project-root resolution for utility tools."""

from pathlib import Path


def get_project_root() -> Path:
    """Return the backend project root directory.

    This module lives at app/tools/utility/project_root.py, so parents[3]
    resolves to the backend directory.
    """
    return Path(__file__).resolve().parents[3]
