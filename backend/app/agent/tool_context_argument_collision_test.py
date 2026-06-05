import pytest

from app.agent.core.executor import ToolExecutor
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.agent.tool_adapter import call_llm_tool, get_react_agent_tool_registry


@pytest.mark.asyncio
async def test_tool_input_named_context_is_not_shadowed_by_execution_context(monkeypatch):
    captured = {}

    class FakeContextArgumentTool:
        name = "fake_context_arg_tool"
        requires_context = False
        category = None
        version = "1.0.0"

        def is_available(self):
            return True

        async def execute(self, pattern, context=None, **kwargs):
            captured["pattern"] = pattern
            captured["context"] = context
            captured["kwargs"] = kwargs
            return {
                "success": True,
                "data": {"context": context},
                "summary": "ok",
            }

    fake_tool = FakeContextArgumentTool()

    def fake_get_tool_data(tool_name):
        if tool_name != fake_tool.name:
            return None
        return {
            "tool": fake_tool,
            "metadata": {"description": "fake"},
            "requires_context": False,
        }

    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.list_tools",
        lambda: [fake_tool.name],
    )
    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_tool",
        lambda tool_name: fake_tool if tool_name == fake_tool.name else None,
    )
    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_tool_data",
        fake_get_tool_data,
    )

    registry = get_react_agent_tool_registry()
    memory_manager = HybridMemoryManager(session_id="context_arg_collision")
    executor = ToolExecutor(
        tool_registry={fake_tool.name: registry[fake_tool.name]},
        memory_manager=memory_manager,
    )

    result = await executor.execute_tool(
        fake_tool.name,
        {"pattern": "case.*image", "context": 3},
    )

    assert result["success"] is True
    assert captured["pattern"] == "case.*image"
    assert captured["context"] == 3


@pytest.mark.asyncio
async def test_call_llm_tool_keeps_context_keyword_for_context_aware_tools(monkeypatch):
    captured = {}

    class FakeContextAwareTool:
        name = "fake_context_aware_tool"
        requires_context = True
        category = None
        version = "1.0.0"

        def is_available(self):
            return True

        async def execute(self, execution_context, pattern, **kwargs):
            captured["execution_context"] = execution_context
            captured["pattern"] = pattern
            captured["kwargs"] = kwargs
            return {
                "success": True,
                "data": {"pattern": pattern},
                "summary": "ok",
            }

    fake_tool = FakeContextAwareTool()
    runtime_context = object()

    def fake_get_tool_data(tool_name):
        if tool_name != fake_tool.name:
            return None
        return {
            "tool": fake_tool,
            "metadata": {"description": "fake"},
            "requires_context": True,
        }

    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_tool",
        lambda tool_name: fake_tool if tool_name == fake_tool.name else None,
    )
    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_tool_data",
        fake_get_tool_data,
    )

    result = await call_llm_tool(
        fake_tool.name,
        context=runtime_context,
        pattern="case.*image",
    )

    assert result["success"] is True
    assert captured["execution_context"] is runtime_context
    assert captured["pattern"] == "case.*image"
    assert "context" not in captured["kwargs"]
