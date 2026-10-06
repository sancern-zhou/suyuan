from app.agent.core.streaming_tool_executor import StreamingToolExecutor
from app.tools.base.tool_interface import LLMTool, ToolCategory


class _Tool(LLMTool):
    def __init__(self, category, **kwargs):
        super().__init__(
            name=f"{category.value}-tool",
            description="test",
            category=category,
            **kwargs,
        )

    async def execute(self, **kwargs):
        return {"success": True}


def test_query_tools_default_to_parallel_read():
    tool = _Tool(ToolCategory.QUERY)
    assert tool.is_read_only({}) is True
    assert tool.concurrency_policy == "parallel_read"


def test_query_tool_can_explicitly_require_serial_execution():
    tool = _Tool(ToolCategory.QUERY, concurrency_policy="serial")
    assert tool.is_read_only({}) is False


def test_streaming_executor_consumes_tool_read_only_contract():
    tool = _Tool(ToolCategory.QUERY)
    executor = StreamingToolExecutor(
        tool_executor=None,
        tool_registry={"query-tool": tool},
    )
    assert executor._is_concurrency_safe("query-tool", {}) is True
