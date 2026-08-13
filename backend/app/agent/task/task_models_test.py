import pytest

from app.agent.task.task_models import TaskList, TaskStatus


def test_task_list_creates_and_updates_single_task_incrementally():
    task_list = TaskList()

    created = task_list.create(
        subject="Inspect task logs",
        description="Review recent runtime logs for repeated task updates",
        active_form="Inspecting task logs",
    )
    updated = task_list.update(created.id, status=TaskStatus.IN_PROGRESS)

    assert created.id == "1"
    assert updated.status == TaskStatus.IN_PROGRESS
    assert task_list.list()[0].status == TaskStatus.IN_PROGRESS


def test_task_list_rejects_multiple_in_progress_tasks():
    task_list = TaskList()
    first = task_list.create("Inspect logs", "Review logs", "Inspecting logs")
    second = task_list.create("Compare Claude", "Review reference", "Comparing Claude")

    task_list.update(first.id, status=TaskStatus.IN_PROGRESS)

    with pytest.raises(ValueError, match="Only one task can be in_progress"):
        task_list.update(second.id, status=TaskStatus.IN_PROGRESS)


def test_task_list_keeps_completed_tasks_visible():
    task_list = TaskList()
    first = task_list.create("Inspect logs", "Review logs", "Inspecting logs")
    second = task_list.create("Summarize", "Write findings", "Summarizing")

    task_list.update(first.id, status=TaskStatus.COMPLETED)
    task_list.update(second.id, status=TaskStatus.COMPLETED)

    assert [task.status for task in task_list.list()] == [
        TaskStatus.COMPLETED,
        TaskStatus.COMPLETED,
    ]
    assert task_list.completed_snapshot() == [
        {
            "id": "1",
            "subject": "Inspect logs",
            "description": "Review logs",
            "activeForm": "Inspecting logs",
            "status": "completed",
        },
        {
            "id": "2",
            "subject": "Summarize",
            "description": "Write findings",
            "activeForm": "Summarizing",
            "status": "completed",
        },
    ]
