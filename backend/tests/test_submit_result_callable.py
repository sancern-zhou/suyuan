"""SubmitResultTool 裸实例注册的调用形态回归测试。

executor 对 registry 值直接 `await tool_func(__execution_context=..., **tool_args)`；
call_sub_agent / 定时任务 `_inject_submit_result` 都以裸实例注册 submit_result，
实例必须可调用（曾报 'SubmitResultTool' object is not callable，交付信封丢失）。

信封准入契约：submit_result 是结构化结果的唯一生产点，从这里交付的
submitted_result 必须永远是 JSON 可序列化对象——下游（交付边界、final_result、
workflow envelope）都直接 json.dumps，不再各自兜底。
"""
import json

import pytest

from app.tools.agent_tools.submit_result_tool import SubmitResultTool, json_safe_envelope


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


@pytest.mark.asyncio
async def test_flat_envelope_excludes_executor_injected_dunder_kwargs():
    """模型平铺提交时，executor 注入的 __execution_context 不得混进结果信封。

    曾因此让 ExecutionContext 进入 submitted_result，交付边界
    json.dumps 抛 "Object of type ExecutionContext is not JSON serializable"，
    废掉整个工作流节点（2026-11-01 广东月报编排 r2 两节点首跑即此因）。
    """
    tool = SubmitResultTool()

    outcome = await tool(
        __execution_context=object(),
        status="completed_with_gaps",
        findings=["a", "b"],
    )

    assert outcome["status"] == "success"
    assert tool.submitted_result == {"status": "completed_with_gaps", "findings": ["a", "b"]}
    json.dumps(tool.submitted_result, ensure_ascii=False)


@pytest.mark.asyncio
async def test_envelope_acceptance_guarantees_json_serializable():
    """信封混入不可序列化对象时在准入点降级，下游 json.dumps 永不失败。"""
    tool = SubmitResultTool()

    await tool(result={"status": "ok", "context": object()})
    assert json.loads(json.dumps(tool.submitted_result, ensure_ascii=False))
    assert tool.submitted_result["status"] == "ok"

    await tool(__execution_context=object(), status="ok", payload={"a": 1})
    assert json.loads(json.dumps(tool.submitted_result, ensure_ascii=False))
    assert tool.submitted_result["status"] == "ok"


def test_json_safe_envelope_rejects_non_dict():
    assert json_safe_envelope("not a dict") is None
    assert json_safe_envelope(None) is None
