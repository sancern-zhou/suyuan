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
async def test_sub_agent_explicitly_inherits_parent_model_chain(monkeypatch):
    parent_service = SimpleNamespace(
        provider="bailian",
        model="deepseek-v4-pro",
        request_fallbacks="agnes/agnes-2.0-flash,minimax/MiniMax-M3",
    )
    child_service = _RecordingLLMService()

    class FakeReActAgent:
        def __init__(self, **kwargs):
            self.planner = SimpleNamespace(llm_service=child_service)

        async def analyze(self, **kwargs):
            assert child_service.active_chain == (
                "bailian",
                "deepseek-v4-pro",
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
            )
            yield {"type": "agent_finish", "answer": "复核完成", "data": {}}

    monkeypatch.setattr("app.agent.react_agent.ReActAgent", FakeReActAgent)
    tool = CallSubAgentTool()
    monkeypatch.setattr(tool, "_update_session", lambda **kwargs: None)

    result = await tool.execute(
        context=_context(
            parent_service,
            model_chain=(
                "bailian",
                "deepseek-v4-pro",
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
            ),
        ),
        target_mode="ops",
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
