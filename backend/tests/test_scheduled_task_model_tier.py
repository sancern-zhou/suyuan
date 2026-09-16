import pytest
from pydantic import ValidationError
from app.scheduled_tasks.models import ScheduledTask
from app.api.scheduled_task_routes import CreateTaskRequest, UpdateTaskRequest


@pytest.mark.parametrize('tier', ['auto', 'flash', 'pro'])
def test_model_tier_round_trip(tier):
    request = CreateTaskRequest(name='test', description='test', prompt='test', schedule_type='daily_8am', model_tier=tier)
    task = ScheduledTask(task_id='tier_test', **request.model_dump(exclude_none=True))
    assert ScheduledTask.model_validate_json(task.model_dump_json()).model_tier == tier
    assert UpdateTaskRequest(model_tier=tier).model_dump(exclude_unset=True) == {'model_tier': tier}


def test_legacy_task_defaults_to_auto():
    task = ScheduledTask(task_id='legacy', name='test', description='test', prompt='test', schedule_type='daily_8am')
    assert task.model_tier == 'auto'
    assert 'model_tier' not in UpdateTaskRequest(name='renamed').model_dump(exclude_unset=True)


@pytest.mark.parametrize('model', [ScheduledTask, CreateTaskRequest, UpdateTaskRequest])
def test_invalid_tier_rejected(model):
    with pytest.raises(ValidationError):
        model(task_id='invalid', name='test', description='test', prompt='test', schedule_type='daily_8am', model_tier='invalid')
