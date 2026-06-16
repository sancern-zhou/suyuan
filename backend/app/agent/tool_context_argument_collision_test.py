import pytest

from app.agent.core.executor import ToolExecutor
from app.agent.core.planner import ReActPlanner
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.agent.tool_adapter import (
    call_llm_tool,
    get_detailed_schemas_for_tools,
    get_react_agent_tool_registry,
    get_tool_schemas,
)


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


def test_chart_read_file_schema_keeps_optional_native_multimodal_attachment(monkeypatch):
    class FakeReadFileTool:
        name = "read_file"

        def is_available(self):
            return True

        def get_function_schema(self):
            return {
                "name": "read_file",
                "description": "读取文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "auto_analyze": {"type": "boolean"},
                        "analysis_type": {"type": "string"},
                    },
                },
            }

    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_all_tools",
        lambda: [{"tool": FakeReadFileTool()}],
    )

    schemas = get_tool_schemas(mode="chart")

    read_file_schema = next(schema for schema in schemas if schema["name"] == "read_file")
    properties = read_file_schema["parameters"]["properties"]
    assert "analysis_type" not in properties
    assert "auto_analyze" not in properties
    assert properties["as_multimodal_attachment"]["default"] is False
    assert "需要查看历史或工具生成的本地图片" in properties["as_multimodal_attachment"]["description"]
    assert "图表模式" in properties["as_multimodal_attachment"]["description"]
    assert "社交模式" in properties["as_multimodal_attachment"]["description"]


def test_chart_detailed_read_file_schema_keeps_optional_native_multimodal_attachment(monkeypatch):
    class FakeReadFileTool:
        name = "read_file"

        def is_available(self):
            return True

        def get_function_schema(self):
            return {
                "name": "read_file",
                "description": "读取文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "auto_analyze": {"type": "boolean"},
                        "analysis_type": {"type": "string"},
                    },
                },
            }

    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_all_tools",
        lambda: [{"tool": FakeReadFileTool()}],
    )

    schemas = get_detailed_schemas_for_tools(["read_file"], mode="chart")

    properties = schemas[0]["parameters"]["properties"]
    assert "analysis_type" not in properties
    assert "auto_analyze" not in properties
    assert properties["as_multimodal_attachment"]["default"] is False


def test_default_detailed_read_file_schema_retains_legacy_image_analysis_fields(monkeypatch):
    class FakeReadFileTool:
        name = "read_file"

        def is_available(self):
            return True

        def get_function_schema(self):
            return {
                "name": "read_file",
                "description": "读取文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "auto_analyze": {"type": "boolean"},
                        "analysis_type": {"type": "string"},
                    },
                },
            }

    monkeypatch.setattr(
        "app.agent.tool_adapter.global_tool_registry.get_all_tools",
        lambda: [{"tool": FakeReadFileTool()}],
    )

    schemas = get_detailed_schemas_for_tools(["read_file"])

    properties = schemas[0]["parameters"]["properties"]
    assert "analysis_type" in properties
    assert "auto_analyze" in properties
    assert "as_multimodal_attachment" not in properties


@pytest.mark.asyncio
async def test_planner_preserves_tool_input_from_streaming_start_block():
    class ToolBlock:
        type = "tool_use"
        id = "toolu_ppt"
        name = "create_pptx_with_ppt_master"
        input = {"title": "测试PPT", "slide_plan": [{"title": "第一页"}]}

    class FakeLLMService:
        provider = "deepseek"
        model = "deepseek-v4-pro"

        async def chat_anthropic_streaming(self, **kwargs):
            yield {"type": "content_block_start", "data": {"index": 0, "block": ToolBlock()}}
            yield {"type": "content_block_stop", "data": {"index": 0}}
            yield {"type": "message_stop", "data": {}}

    planner = ReActPlanner(llm_client=FakeLLMService())

    tool_inputs = []
    actions = []
    async for event in planner.think_and_action_streaming(
        query="生成PPT",
        system_prompt="system",
        user_conversation="user",
        tools=[],
        iteration=1,
        mode="assistant",
    ):
        if event["type"] == "tool_use":
            tool_inputs.append(event["data"]["input"])
        if event["type"] == "action":
            actions.append(event["data"]["action"])

    assert tool_inputs == [{"title": "测试PPT", "slide_plan": [{"title": "第一页"}]}]
    assert actions[0]["args"]["title"] == "测试PPT"


@pytest.mark.asyncio
async def test_planner_preserves_tool_input_from_streaming_json_delta():
    class ToolBlock:
        type = "tool_use"
        id = "toolu_read"
        name = "read_file"

    class Delta:
        type = "input_json_delta"
        partial_json = '{"path": "/tmp/a.txt"}'

    class FakeLLMService:
        provider = "anthropic"
        model = "claude"

        async def chat_anthropic_streaming(self, **kwargs):
            yield {"type": "content_block_start", "data": {"index": 0, "block": ToolBlock()}}
            yield {"type": "content_block_delta", "data": {"index": 0, "delta": Delta()}}
            yield {"type": "content_block_stop", "data": {"index": 0}}
            yield {"type": "message_stop", "data": {}}

    planner = ReActPlanner(llm_client=FakeLLMService())

    tool_inputs = []
    async for event in planner.think_and_action_streaming(
        query="读文件",
        system_prompt="system",
        user_conversation="user",
        tools=[],
        iteration=1,
        mode="assistant",
    ):
        if event["type"] == "tool_use":
            tool_inputs.append(event["data"]["input"])

    assert tool_inputs == [{"path": "/tmp/a.txt"}]


@pytest.mark.asyncio
async def test_planner_does_not_execute_tool_when_streaming_json_delta_is_malformed():
    class ToolBlock:
        type = "tool_use"
        id = "toolu_bad_ppt"
        name = "create_pptx_with_ppt_master"

    class Delta:
        type = "input_json_delta"
        partial_json = '{"title": "长PPT", "slide_plan": [{"title"'

    class FakeLLMService:
        provider = "deepseek"
        model = "deepseek-v4-pro"

        async def chat_anthropic_streaming(self, **kwargs):
            yield {"type": "content_block_start", "data": {"index": 0, "block": ToolBlock()}}
            yield {"type": "content_block_delta", "data": {"index": 0, "delta": Delta()}}
            yield {"type": "content_block_stop", "data": {"index": 0}}
            yield {"type": "message_stop", "data": {}}

    planner = ReActPlanner(llm_client=FakeLLMService())

    tool_use_events = []
    actions = []
    async for event in planner.think_and_action_streaming(
        query="生成长PPT",
        system_prompt="system",
        user_conversation="user",
        tools=[],
        iteration=1,
        mode="assistant",
    ):
        if event["type"] == "tool_use":
            tool_use_events.append(event)
        if event["type"] == "action":
            actions.append(event["data"]["action"])

    assert tool_use_events == []
    assert actions[0]["type"] == "PLAIN_TEXT_REPLY"
    assert "create_pptx_with_ppt_master" in actions[0]["answer"]
    assert "tool input JSON" in actions[0]["answer"]
