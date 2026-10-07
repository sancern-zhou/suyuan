from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio
import pytest
from pydantic import ValidationError
from app.scheduled_tasks.models import ScheduledTask, TaskExecution
from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.storage import TaskStorage, ExecutionStorage


def task(**changes):
    return ScheduledTask(**dict(dict(task_id='config-test', name='配置测试', description='测试',
        prompt='核验事实', schedule_type='daily_8am', history_learning={'enabled': False}), **changes))


@pytest.mark.parametrize('changes', [dict(model_tier='unknown'), dict(result_requirements=[
    dict(field='sections.level', label='等级'), dict(field='sections.level', label='重复')]),
    dict(result_requirements=[dict(field='sections.level', label='等级', allowed_values=[''])]),
    dict(result_requirements=[dict(field='not_a_field', label='未知')])])
def test_invalid_config_rejected(changes):
    with pytest.raises(ValidationError):
        task(**changes)


def test_configuration_survives_storage_and_is_injected(tmp_path):
    configured = task(model_tier='pro', result_requirements=[dict(field='sections.level', label='等级', allowed_values=['P1'])])
    storage = TaskStorage(str(tmp_path)); storage.create(configured)
    restored = storage.get(configured.task_id)
    assert restored.model_tier == 'pro'
    executor = ScheduledTaskExecutor(storage, ExecutionStorage(str(tmp_path)))
    execution = TaskExecution(execution_id='execution', task_id=restored.task_id, task_name=restored.name, status='running', total_steps=1)
    metadata = executor._runtime_metadata(restored, execution)['scheduled_task']
    assert metadata['result_requirements'][0]['allowed_values'] == ['P1']
    assert metadata['model_tier'] == 'pro'
    assert 'sections.level' in executor._build_task_prompt(restored.prompt, restored)


@pytest.mark.asyncio
async def test_concurrent_model_tiers_are_scoped_to_execution(tmp_path, monkeypatch):
    from app.services.llm_service import llm_service
    current = ContextVar('test_tier', default='auto')
    @contextmanager
    def select(tier):
        token = current.set(tier)
        try: yield
        finally: current.reset(token)
    monkeypatch.setattr(llm_service, 'use_model_tier', select)
    executor = ScheduledTaskExecutor(TaskStorage(str(tmp_path)), ExecutionStorage(str(tmp_path)),
        conversation_persistence=SimpleNamespace(ensure_terminal_session=AsyncMock(), publish_conversation=AsyncMock()))
    seen = {}
    async def run(prompt, session_id, **kwargs):
        await asyncio.sleep(0)
        seen[kwargs['task'].task_id] = current.get()
        return dict(summary='完成', data_ids=[], visuals=[], thoughts=[], tool_calls=[], iterations=1)
    monkeypatch.setattr(executor, '_run_agent', run)
    tasks = [task(task_id=tier, model_tier=tier) for tier in ['auto', 'flash', 'pro']]
    await asyncio.gather(*(executor.execute_task(item, update_stats=False) for item in tasks))
    assert seen == {tier: tier for tier in ['auto', 'flash', 'pro']}
    assert current.get() == 'auto'


@pytest.mark.asyncio
async def test_completed_execution_persists_structured_result(tmp_path, monkeypatch):
    class RecordingResultStorage:
        def __init__(self):
            self.results = []

        def upsert(self, result):
            self.results.append(result)
            return result

    result_storage = RecordingResultStorage()
    persistence = SimpleNamespace(
        ensure_terminal_session=AsyncMock(),
        publish_conversation=AsyncMock(),
    )
    executor = ScheduledTaskExecutor(
        TaskStorage(str(tmp_path)),
        ExecutionStorage(str(tmp_path)),
        conversation_persistence=persistence,
        task_result_storage=result_storage,
    )

    async def run(prompt, session_id, **kwargs):
        return dict(
            summary='空气质量保持稳定',
            data_ids=[],
            visuals=[],
            thoughts=[],
            tool_calls=[],
            iterations=1,
        )

    monkeypatch.setenv('SCHEDULED_TASK_RESULT_STORAGE', 'on')
    monkeypatch.setattr(executor, '_run_agent', run)

    execution = await executor.execute_task(task(), update_stats=False)

    assert execution.status.value == 'success'
    assert len(result_storage.results) == 1
    assert result_storage.results[0].execution_id == execution.execution_id
    assert result_storage.results[0].conclusion == '空气质量保持稳定'
