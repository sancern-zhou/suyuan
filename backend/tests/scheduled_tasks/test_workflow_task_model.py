import pytest

from app.scheduled_tasks.models.task import ScheduleType, ScheduledTask


def _base(**overrides):
    payload = {
        "task_id": "workflow_task",
        "name": "确定性工作流",
        "description": "确定性工作流任务",
        "execution_mode": "workflow",
        "workflow_name": "demo_workflow",
        "schedule_type": "daily_8am",
        "prompt": "执行确定性工作流",
    }
    payload.update(overrides)
    return payload


def test_workflow_mode_requires_workflow_name():
    with pytest.raises(ValueError):
        ScheduledTask(**_base(workflow_name=None))


def test_workflow_fields_rejected_for_agent_modes():
    with pytest.raises(ValueError):
        ScheduledTask(**_base(execution_mode="expert", workflow_name="demo_workflow"))


def test_workflow_task_round_trips_with_model_tier():
    task = ScheduledTask(**_base(model_tier="pro"))

    restored = ScheduledTask.model_validate_json(task.model_dump_json())

    assert restored.execution_mode == "workflow"
    assert restored.workflow_name == "demo_workflow"
    assert restored.model_tier == "pro"


@pytest.mark.parametrize("schedule_type", ["monthly_custom", "quarterly_custom"])
def test_monthly_and_quarterly_require_day_of_month(schedule_type):
    task = ScheduledTask(
        **_base(
            workflow_name=None,
            execution_mode="expert",
            schedule_type=schedule_type,
            day_of_month=5,
            hour=7,
            minute=30,
        )
    )

    assert task.schedule_type == ScheduleType(schedule_type)
    assert task.day_of_month == 5

    with pytest.raises(ValueError):
        ScheduledTask(
            **_base(
                workflow_name=None,
                execution_mode="expert",
                schedule_type=schedule_type,
                hour=7,
                minute=30,
            )
        )
