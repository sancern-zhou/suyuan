import pytest
from pydantic import ValidationError

from app.scheduled_tasks.models import ScheduledTask


def make_task(**overrides):
    data = {
        "task_id": "custom-task",
        "name": "自定义任务",
        "description": "只使用指定工具",
        "execution_mode": "custom",
        "tool_names": ["read_file", "write_file"],
        "schedule_type": "once",
        "run_at": "2026-07-20T12:00:00",
        "prompt": "执行",
    }
    data.update(overrides)
    return ScheduledTask(**data)


def test_custom_task_normalizes_duplicate_tools_in_user_order():
    task = make_task(tool_names=["write_file", "read_file", "write_file"])

    assert task.tool_names == ["write_file", "read_file"]


def test_custom_task_requires_at_least_one_tool():
    with pytest.raises(ValidationError, match="tool_names is required for custom mode"):
        make_task(tool_names=[])


def test_non_custom_task_rejects_tool_names():
    with pytest.raises(ValidationError, match="tool_names is only valid for custom mode"):
        make_task(execution_mode="assistant")

    with pytest.raises(ValidationError, match="tool_names is only valid for custom mode"):
        make_task(execution_mode="assistant", tool_names=[])


def test_legacy_task_without_tool_names_remains_valid():
    task = make_task(execution_mode="assistant", tool_names=None)

    assert task.tool_names is None
