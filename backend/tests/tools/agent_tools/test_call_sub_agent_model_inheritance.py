from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


class _RecordingLLMService:
    def __init__(self) -> None:
        self.provider = "default"
        self.model = "default-model"
        self.request_fallbacks = "default/fallback"
        self.active_chain = None
        self.entered_chains = []

    @contextmanager
    def use_provider_chain(self, provider, model, fallbacks):
        chain = (provider, model, fallbacks)
        self.entered_chains.append(chain)
        self.active_chain = chain
        try:
            yield
        finally:
            self.active_chain = None


def _context(parent_llm_service, model_chain=None):
    tool_executor = SimpleNamespace(tool_registry={})
    if model_chain is not None:
        tool_executor.llm_model_chain = model_chain
    return SimpleNamespace(
        manual_mode="ops",
        llm_planner=SimpleNamespace(llm_service=parent_llm_service),
        tool_executor=tool_executor,
    )


@pytest.mark.asyncio
async def test_stale_upstream_resource_cannot_trigger_child_model_or_refetch(monkeypatch, tmp_path):
    from app.agent.resources.resource_service import SessionResourceService
    constructed = []

    class FakeReActAgent:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            raise AssertionError("child must not start with missing contracted input")

    monkeypatch.setattr("app.agent.react_agent.ReActAgent", FakeReActAgent)
    monkeypatch.setattr("app.agent.workflow.resource_handoff.get_data_registry", lambda: tmp_path)
    source = tmp_path / "air.json"
    source.write_text('[{"pm25": 42}]', encoding="utf-8")
    context = _context(SimpleNamespace(provider="test", model="test", request_fallbacks=""))
    context.tool_executor.resource_service = SessionResourceService.in_memory()
    tool = CallSubAgentTool()
    monkeypatch.setattr(tool, "_update_session", lambda **kwargs: None)
    result = await tool.execute(
        context=context, target_mode="ops", goal="reuse upstream only", force_new_session=True,
        _upstream_handles=[{"source_task_id": "air", "source_session_id": "source", "resource_id": "stale", "file_path": str(source)},
                           {"source_task_id": "air", "file_path": str(source)}],
        _input_contracts=[{"source_task_id": "air", "fields": ["pm25"]}],
    )
    assert constructed == []
    assert result["success"] is False
    assert result["data"]["resource_contract_violations"][0]["code"] == "resource_missing"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_mode", ["ops", "office"])
@pytest.mark.parametrize("client_channel", ["web", "app"])
async def test_sub_agent_explicitly_inherits_parent_model_chain(monkeypatch, target_mode, client_channel):
    parent_service = SimpleNamespace(
        provider="bailian",
        model="deepseek-v4-pro",
        request_fallbacks="agnes/agnes-2.0-flash,minimax/MiniMax-M3",
    )
    child_service = _RecordingLLMService()

    class FakeReActAgent:
        def __init__(self, **kwargs):
            self.planner = SimpleNamespace(llm_service=child_service)
            if target_mode == "office":
                assert set(kwargs["tool_registry"]) == {"execute_python"}

        async def analyze(self, **kwargs):
            assert kwargs["manual_mode"] == target_mode
            assert kwargs["runtime_metadata"]["client_channel"] == client_channel
            assert child_service.active_chain == (
                "bailian",
                "deepseek-v4-pro",
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
            )
            yield {"type": "agent_finish", "answer": "复核完成", "data": {}}

    monkeypatch.setattr("app.agent.react_agent.ReActAgent", FakeReActAgent)
    tool = CallSubAgentTool()
    monkeypatch.setattr(tool, "_update_session", lambda **kwargs: None)
    monkeypatch.setattr(tool, "_persist_workflow_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(tool, "_persist_turn_start", lambda **kwargs: None)
    context = _context(
            parent_service,
            model_chain=(
                "bailian",
                "deepseek-v4-pro",
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
            ),
        )
    context.runtime_metadata = {"client_channel": client_channel}
    if target_mode == "office":
        context.manual_mode = "assistant"
        context.tool_executor.delegation_tool_registry = {
            "execute_python": object(), "execute_sql_query": object(),
            "call_sub_agent": object(), "create_report_package": object(),
        }
    result = await tool.execute(
        context=context,
        target_mode=target_mode,
        goal="复核工单",
        force_new_session=True,
    )

    assert result["success"] is True
    assert child_service.entered_chains == [
        (
            "bailian",
            "deepseek-v4-pro",
            "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
        )
    ]


@pytest.mark.asyncio
async def test_sub_agent_internal_failure_is_returned_as_tool_failure(monkeypatch):
    child_service = _RecordingLLMService()

    class FakeReActAgent:
        def __init__(self, **kwargs):
            self.planner = SimpleNamespace(llm_service=child_service)

        async def analyze(self, **kwargs):
            if False:
                yield {}

    monkeypatch.setattr("app.agent.react_agent.ReActAgent", FakeReActAgent)
    tool = CallSubAgentTool()
    monkeypatch.setattr(tool, "_update_session", lambda **kwargs: None)

    result = await tool.execute(
        context=_context(
            SimpleNamespace(
                provider="bailian",
                model="qwen3.8-max-preview",
                request_fallbacks="mimo/mimo-v2.5",
            )
        ),
        target_mode="ops",
        goal="复核工单",
        force_new_session=True,
    )

    assert result["status"] == "failed"
    assert result["success"] is False
    assert result["result"] == "子Agent未返回结果"
