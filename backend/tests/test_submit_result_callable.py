"""SubmitResultTool 裸实例注册的调用形态回归测试。

executor 对 registry 值直接 `await tool_func(__execution_context=..., **tool_args)`；
call_sub_agent / 定时任务 `_inject_submit_result` 都以裸实例注册 submit_result，
实例必须可调用（曾报 'SubmitResultTool' object is not callable，交付信封丢失）。
"""
import pytest

from app.tools.agent_tools.submit_result_tool import SubmitResultTool


@pytest.mark.asyncio
async def test_instance_is_directly_awaitable_like_executor_does():
    tool = SubmitResultTool({"type": "object", "properties": {"result": {"type": "object"}}})

    # 模拟 executor.execute_tool 的调用形态：注入 __execution_context 关键字参数
    outcome = await tool(__execution_context=object(), result={"answer": 42})

    assert outcome["status"] == "success"
    assert tool.submitted_result == {"answer": 42}


@pytest.mark.asyncio
async def test_execute_without_result_keeps_envelope_none():
    tool = SubmitResultTool()
    outcome = await tool()
    assert outcome["success"] is True
    assert tool.submitted_result is None
