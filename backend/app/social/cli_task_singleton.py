"""Global singleton for background CLI task manager."""

from __future__ import annotations

from typing import Optional

from app.social.cli_task_manager import CliTaskManager

_cli_task_manager: Optional[CliTaskManager] = None


def set_cli_task_manager(manager: CliTaskManager) -> None:
    global _cli_task_manager
    _cli_task_manager = manager


def get_cli_task_manager() -> Optional[CliTaskManager]:
    return _cli_task_manager
