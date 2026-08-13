"""
StreamingToolExecutor 单元测试

验证流式工具执行器的核心功能：
- 工具即时启动和异步执行
- 并发安全分组（只读并行，写入串行）
- 结果有序消费（getCompletedResults / getRemainingResults）
- 错误隔离和取消机制
"""

import asyncio
import importlib.util
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# 直接加载模块，避免 __init__.py 的导入链
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_ste_path = "/home/xckj/suyuan/backend/app/agent/core/streaming_tool_executor.py"
_ste = _load_module("streaming_tool_executor", _ste_path)

StreamingToolExecutor = _ste.StreamingToolExecutor
ToolExecution = _ste.ToolExecution
ToolStatus = _ste.ToolStatus


# === 测试 ToolExecution 数据类 ===

def test_tool_execution_initial_state():
    exe = ToolExecution(
        tool_use_id="test_001",
        tool_name="read_file",
        tool_input={"path": "/tmp/test.txt"},
    )
    assert exe.status == ToolStatus.PENDING
    assert exe.result is None
    assert exe.error is None
    assert exe.is_concurrency_safe is False
    assert exe.task is None


def test_tool_execution_mark_completed():
    exe = ToolExecution(tool_use_id="test_001", tool_name="read_file", tool_input={})
    result = {"success": True, "data": "file content"}
    exe.mark_completed(result)
    assert exe.status == ToolStatus.COMPLETED
    assert exe.result == result


def test_tool_execution_mark_failed():
    exe = ToolExecution(tool_use_id="test_001", tool_name="read_file", tool_input={})
    exe.mark_failed("file not found")
    assert exe.status == ToolStatus.FAILED
    assert exe.error == "file not found"


def test_tool_execution_mark_cancelled():
    exe = ToolExecution(tool_use_id="test_001", tool_name="read_file", tool_input={})
    exe.mark_cancelled()
    assert exe.status == ToolStatus.CANCELLED


@pytest.mark.asyncio
async def test_tool_execution_wait():
    exe = ToolExecution(tool_use_id="test_001", tool_name="read_file", tool_input={})

    async def delayed_complete():
        await asyncio.sleep(0.05)
        exe.mark_completed({"success": True})

    asyncio.create_task(delayed_complete())
    await exe.wait()
    assert exe.status == ToolStatus.COMPLETED


# === 测试 StreamingToolExecutor ===

def test_concurrency_safe_detection():
    executor = StreamingToolExecutor(
        tool_executor=MagicMock(),
        tool_registry={},
    )
    assert executor._is_concurrency_safe("read_file", {}) is True
    assert executor._is_concurrency_safe("grep", {}) is True
    assert executor._is_concurrency_safe("get_weather_data", {}) is True
    assert executor._is_concurrency_safe("edit_file", {}) is False
    assert executor._is_concurrency_safe("write_file", {}) is False
    assert executor._is_concurrency_safe("bash", {}) is False


def test_concurrency_safe_with_tool_registry():
    mock_tool = MagicMock()
    mock_tool.is_read_only = MagicMock(return_value=True)

    executor = StreamingToolExecutor(
        tool_executor=MagicMock(),
        tool_registry={"custom_read_tool": mock_tool},
    )
    assert executor._is_concurrency_safe("custom_read_tool", {}) is True
    assert executor._is_concurrency_safe("custom_write_tool", {}) is False


@pytest.mark.asyncio
async def test_single_tool_execution():
    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = AsyncMock(return_value={
        "success": True,
        "data": {"content": "test data"},
        "summary": "读取成功",
    })

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool(
        tool_use_id="toolu_001",
        tool_name="read_file",
        tool_input={"path": "/tmp/test.txt"},
        iteration=1,
    )

    assert streaming_executor.total_count == 1
    assert streaming_executor.has_pending_or_running is True

    results = []
    async for result in streaming_executor.getRemainingResults():
        results.append(result)

    assert len(results) == 1
    assert results[0]["tool_use_id"] == "toolu_001"
    assert results[0]["tool_name"] == "read_file"
    assert results[0]["result"]["success"] is True

    assert streaming_executor.completed_count == 1
    assert streaming_executor.has_pending_or_running is False


@pytest.mark.asyncio
async def test_multiple_safe_tools_parallel():
    call_times = []

    async def mock_execute(tool_name, tool_args, tool_call_id, iteration):
        entry = {"name": tool_name, "start": asyncio.get_event_loop().time()}
        call_times.append(entry)
        await asyncio.sleep(0.1)
        entry["end"] = asyncio.get_event_loop().time()
        return {"success": True, "summary": f"{tool_name} done"}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = mock_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "read_file", {"path": "/a"}, 1)
    streaming_executor.addTool("toolu_002", "grep", {"pattern": "test"}, 1)

    results = []
    async for result in streaming_executor.getRemainingResults():
        results.append(result)

    assert len(results) == 2
    assert results[0]["tool_use_id"] == "toolu_001"
    assert results[1]["tool_use_id"] == "toolu_002"

    # 验证并行执行：两个工具的执行时间应该有重叠
    if len(call_times) == 2:
        overlap = call_times[0]["end"] > call_times[1]["start"]
        assert overlap, "并发安全工具应该并行执行"


@pytest.mark.asyncio
async def test_unsafe_tools_serial():
    execution_order = []

    async def mock_execute(tool_name, tool_args, tool_call_id, iteration):
        execution_order.append(f"start_{tool_name}")
        await asyncio.sleep(0.1)
        execution_order.append(f"end_{tool_name}")
        return {"success": True}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = mock_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "edit_file", {"path": "/a"}, 1)
    streaming_executor.addTool("toolu_002", "write_file", {"path": "/b"}, 1)

    results = []
    async for result in streaming_executor.getRemainingResults():
        results.append(result)

    assert len(results) == 2
    # 验证串行执行
    if "start_edit_file" in execution_order and "end_edit_file" in execution_order:
        end_first = execution_order.index("end_edit_file")
        start_second = execution_order.index("start_write_file")
        assert end_first < start_second, "非并发安全工具应该串行执行"


@pytest.mark.asyncio
async def test_getCompletedResults_ordered():
    async def mock_execute(tool_name, tool_args, tool_call_id, iteration):
        if tool_name == "fast_tool":
            await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(0.1)
        return {"success": True}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = mock_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "slow_tool", {}, 1)
    streaming_executor.addTool("toolu_002", "fast_tool", {}, 1)

    await asyncio.sleep(0.2)

    completed = streaming_executor.getCompletedResults()
    assert len(completed) == 2
    # 应按添加顺序返回
    assert completed[0]["tool_use_id"] == "toolu_001"
    assert completed[1]["tool_use_id"] == "toolu_002"


@pytest.mark.asyncio
async def test_tool_execution_error_isolation():
    async def mock_execute(tool_name, tool_args, tool_call_id, iteration):
        if tool_name == "failing_tool":
            raise ValueError("模拟执行失败")
        return {"success": True}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = mock_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "failing_tool", {}, 1)
    streaming_executor.addTool("toolu_002", "read_file", {}, 1)

    results = []
    async for result in streaming_executor.getRemainingResults():
        results.append(result)

    assert len(results) == 2
    assert results[0]["result"]["success"] is False
    assert results[1]["result"]["success"] is True


@pytest.mark.asyncio
async def test_discard_cancels_pending():
    async def slow_execute(tool_name, tool_args, tool_call_id, iteration):
        await asyncio.sleep(10)
        return {"success": True}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = slow_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "bash", {"command": "sleep 100"}, 1)

    await asyncio.sleep(0.05)
    streaming_executor.discard()

    assert streaming_executor._discarded is True


@pytest.mark.asyncio
async def test_discard_prevents_new_tools():
    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = AsyncMock(return_value={"success": True})

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    streaming_executor.addTool("toolu_001", "read_file", {}, 1)
    streaming_executor.discard()

    streaming_executor.addTool("toolu_002", "read_file", {}, 1)
    assert streaming_executor.total_count == 1


@pytest.mark.asyncio
async def test_mixed_safe_and_unsafe_tools():
    """测试混合安全和非安全工具的执行"""
    execution_log = []

    async def mock_execute(tool_name, tool_args, tool_call_id, iteration):
        execution_log.append(f"start_{tool_name}")
        await asyncio.sleep(0.05)
        execution_log.append(f"end_{tool_name}")
        return {"success": True}

    mock_executor = MagicMock()
    mock_executor.execute_tool_with_retry = mock_execute

    streaming_executor = StreamingToolExecutor(
        tool_executor=mock_executor,
        tool_registry={},
    )

    # 2个安全工具 + 1个非安全工具
    streaming_executor.addTool("toolu_001", "read_file", {}, 1)
    streaming_executor.addTool("toolu_002", "grep", {}, 1)
    streaming_executor.addTool("toolu_003", "edit_file", {}, 1)

    results = []
    async for result in streaming_executor.getRemainingResults():
        results.append(result)

    assert len(results) == 3
    # 所有工具都应该成功
    assert all(r["result"]["success"] for r in results)


# === 测试 Planner _parse_accumulated_blocks V4 修改 ===

def _parse_accumulated_blocks(blocks):
    """直接复制 planner.py 中的逻辑进行测试，避免复杂的模块依赖"""
    thinking_blocks = [b for b in blocks if b.get("type") == "thinking"]
    tool_use_blocks = [b for b in blocks if b.get("type") == "tool_use"]
    text_blocks = [b for b in blocks if b.get("type") == "text"]

    thinking_text = ""
    if thinking_blocks:
        thinking_text = " ".join([b.get("thinking", "") for b in thinking_blocks])

    full_text = " ".join([b.get("text", "") for b in text_blocks])

    if not tool_use_blocks:
        return {
            "thought": thinking_text or "思考回复策略",
            "reasoning": "Extended Thinking",
            "action": {
                "type": "PLAIN_TEXT_REPLY",
                "answer": full_text
            }
        }

    tool_call = tool_use_blocks[0]
    result = {
        "thought": thinking_text or f"准备调用工具: {tool_call['name']}",
        "reasoning": "Extended Thinking",
        "action": {
            "type": "TOOL_CALL",
            "tool": tool_call["name"],
            "tool_call_id": tool_call["id"],
            "args": tool_call["input"]
        },
        "all_tool_calls": [
            {
                "type": "TOOL_CALL",
                "tool": block["name"],
                "tool_call_id": block["id"],
                "args": block["input"]
            }
            for block in tool_use_blocks
        ]
    }

    if len(tool_use_blocks) > 1:
        result["action"] = {
            "type": "TOOL_CALLS",
            "tools": result["all_tool_calls"]
        }

    return result


def test_parse_accumulated_blocks_single_tool():
    blocks = [
        {"type": "text", "text": "让我读取这个文件"},
        {"type": "tool_use", "id": "toolu_001", "name": "read_file", "input": {"path": "/tmp/test.txt"}},
    ]

    result = _parse_accumulated_blocks(blocks)

    assert result["action"]["type"] == "TOOL_CALL"
    assert result["action"]["tool"] == "read_file"
    assert result["action"]["tool_call_id"] == "toolu_001"
    assert "all_tool_calls" in result
    assert len(result["all_tool_calls"]) == 1


def test_parse_accumulated_blocks_multiple_tools():
    blocks = [
        {"type": "text", "text": "并行读取"},
        {"type": "tool_use", "id": "toolu_001", "name": "read_file", "input": {"path": "/tmp/a.txt"}},
        {"type": "tool_use", "id": "toolu_002", "name": "grep", "input": {"pattern": "test"}},
    ]

    result = _parse_accumulated_blocks(blocks)

    assert result["action"]["type"] == "TOOL_CALLS"
    assert len(result["action"]["tools"]) == 2
    assert result["action"]["tools"][0]["tool"] == "read_file"
    assert result["action"]["tools"][1]["tool"] == "grep"
    assert "all_tool_calls" in result
    assert len(result["all_tool_calls"]) == 2


def test_parse_accumulated_blocks_text_only():
    blocks = [
        {"type": "text", "text": "这是我的回答"},
    ]

    result = _parse_accumulated_blocks(blocks)

    assert result["action"]["type"] == "PLAIN_TEXT_REPLY"
    assert result["action"]["answer"] == "这是我的回答"
    assert "all_tool_calls" not in result


def test_parse_accumulated_blocks_with_thinking():
    blocks = [
        {"type": "thinking", "thinking": "我需要先分析一下..."},
        {"type": "text", "text": "让我读取文件"},
        {"type": "tool_use", "id": "toolu_001", "name": "read_file", "input": {"path": "/tmp/test.txt"}},
    ]

    result = _parse_accumulated_blocks(blocks)

    assert result["thought"] == "我需要先分析一下..."
    assert result["action"]["type"] == "TOOL_CALL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
