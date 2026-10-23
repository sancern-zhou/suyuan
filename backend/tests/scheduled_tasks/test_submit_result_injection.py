"""定时子 Agent 的 submit_result 交付注入。"""

from types import SimpleNamespace

from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor as TaskExecutor


def _agent(registry):
    return SimpleNamespace(executor=SimpleNamespace(tool_registry=registry))


def test_fixed_workflow_mode_injects_submit_result():
    registry = {}
    agent = _agent(registry)
    tool = TaskExecutor._inject_submit_result(agent, "query_forecast")
    assert tool is not None
    assert registry["submit_result"] is tool
    assert TaskExecutor._inject_submit_result(agent, "query_forecast") is tool


def test_non_workflow_mode_not_injected():
    registry = {}
    agent = _agent(registry)
    assert TaskExecutor._inject_submit_result(agent, "office") is None
    assert TaskExecutor._inject_submit_result(agent, "expert_meteorology") is None
    assert "submit_result" not in registry


def test_bad_registry_tolerated():
    agent = SimpleNamespace(executor=SimpleNamespace(tool_registry=None))
    assert TaskExecutor._inject_submit_result(agent, "query_forecast") is None
    assert TaskExecutor._inject_submit_result(None, "query_forecast") is None
