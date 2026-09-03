"""
测试定时任务上下文连续性

验证任务执行使用统一的 session_id，实现上下文连续
"""
import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime

from app.scheduled_tasks.models import ScheduledTask, ScheduleType
from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.storage import TaskStorage, ExecutionStorage


class MockAgent:
    """模拟 ReAct Agent"""

    def __init__(self):
        self.analyze_calls = []  # 记录所有 analyze 调用
        self.session_context = {}  # 模拟会话上下文存储

    async def analyze(self, prompt: str, session_id: str = None, **kwargs):
        """
        模拟 Agent 分析过程

        记录调用参数，验证 session_id 是否正确传递
        """
        call_record = {
            "prompt": prompt,
            "session_id": session_id,
            "timestamp": datetime.now()
        }
        self.analyze_calls.append(call_record)

        # 模拟会话上下文：如果是同一个 session_id，可以访问之前的数据
        if session_id:
            if session_id not in self.session_context:
                self.session_context[session_id] = {"data_ids": []}

            # 模拟生成数据
            data_id = f"data_{len(self.session_context[session_id]['data_ids']) + 1}"
            self.session_context[session_id]["data_ids"].append(data_id)

            # 模拟事件流
            events = [
                {"type": "thought", "content": f"执行提示: {prompt[:50]}"},
                {"type": "tool_call", "tool_name": "mock_tool", "args": {}},
                {
                    "type": "tool_result",
                    "tool_name": "mock_tool",
                    "success": True,
                    "summary": f"任务执行，session_id={session_id}"
                },
                {"type": "data_saved", "data_id": data_id},
                {
                    "type": "final_response",
                    "content": f"已完成任务，可访问的数据: {self.session_context[session_id]['data_ids']}"
                }
            ]

            for event in events:
                yield event
        else:
            # 没有 session_id，模拟新会话
            yield {"type": "error", "content": "未提供 session_id"}


@pytest.mark.asyncio
async def test_scheduled_task_context_continuity():
    """
    测试定时任务的上下文连续性

    验证点：
    1. 整个任务执行使用统一的 session_id
    2. Agent 收到的提示词包含任务级 prompt
    """
    # 创建临时存储目录
    temp_dir = tempfile.mkdtemp()

    try:
        # 创建模拟 Agent 实例
        mock_agent = MockAgent()

        def mock_agent_factory():
            return mock_agent

        # 初始化存储和执行器（使用临时目录）
        task_storage = TaskStorage(storage_dir=temp_dir)
        execution_storage = ExecutionStorage(storage_dir=temp_dir)
        executor = ScheduledTaskExecutor(
            task_storage=task_storage,
            execution_storage=execution_storage,
            agent_factory=mock_agent_factory
        )

        # 一个任务就是一次完整的 Agent 执行，由 Agent 自行规划
        task = ScheduledTask(
            task_id="test_task_001",
            name="测试上下文连续性",
            description="验证任务执行的上下文连续性",
            schedule_type=ScheduleType.ONCE,
            prompt="查询广州昨天的O3浓度数据，分析趋势并生成综合报告",
            timeout_seconds=360,
        )

        # 保存任务到存储（必须先保存，否则 execute_task 会在更新统计时找不到任务）
        task_storage.create(task)

        # 执行任务
        execution = await executor.execute_task(task)

        # 验证：任务执行成功
        assert execution.status.value == "success", f"任务执行失败: {execution.error_message}"
        assert execution.completed_steps == 1, f"完成步骤数不正确: {execution.completed_steps}"

        # 验证：任务有 session_id
        assert execution.session_id is not None, "任务未生成 session_id"
        assert execution.session_id.startswith("scheduled_task_"), f"session_id 格式不正确: {execution.session_id}"

        # 验证：执行使用任务级 session_id
        assert len(mock_agent.analyze_calls) == 1, f"Agent 调用次数不正确: {len(mock_agent.analyze_calls)}"

        call = mock_agent.analyze_calls[0]
        assert call["session_id"] == execution.session_id, "执行的 session_id 与任务不一致"

        # 验证：任务级 prompt 正确传递
        assert "查询广州昨天的O3浓度数据" in call["prompt"]

        # 验证：执行过程中产生的数据挂在会话上下文
        session_id = execution.session_id
        assert session_id in mock_agent.session_context, "会话上下文未创建"
        context_data = mock_agent.session_context[session_id]
        assert len(context_data["data_ids"]) == 1, f"上下文数据数量不正确: {context_data}"

        print("\n[PASS] 上下文连续性测试通过")
        print(f"   - 任务 session_id: {execution.session_id}")
        print(f"   - 数据 IDs: {context_data['data_ids']}")

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_different_tasks_different_sessions():
    """
    测试不同任务使用不同的 session_id

    验证点：
    1. 不同任务执行时生成不同的 session_id
    2. 任务之间的上下文不会互相干扰
    """
    # 创建临时存储目录
    temp_dir = tempfile.mkdtemp()

    try:
        mock_agent = MockAgent()

        def mock_agent_factory():
            return mock_agent

        task_storage = TaskStorage(storage_dir=temp_dir)
        execution_storage = ExecutionStorage(storage_dir=temp_dir)
        executor = ScheduledTaskExecutor(
            task_storage=task_storage,
            execution_storage=execution_storage,
            agent_factory=mock_agent_factory
        )

        # 创建第一个任务
        task1 = ScheduledTask(
            task_id="task_001",
            name="任务1",
            description="第一个任务",
            schedule_type=ScheduleType.ONCE,
            prompt="执行任务1",
            timeout_seconds=60,
        )

        # 创建第二个任务
        task2 = ScheduledTask(
            task_id="task_002",
            name="任务2",
            description="第二个任务",
            schedule_type=ScheduleType.ONCE,
            prompt="执行任务2",
            timeout_seconds=60,
        )

        # 保存任务到存储
        task_storage.create(task1)
        task_storage.create(task2)

        # 执行两个任务
        execution1 = await executor.execute_task(task1)
        execution2 = await executor.execute_task(task2)

        # 验证：两个任务有不同的 session_id
        assert execution1.session_id != execution2.session_id, "不同任务使用了相同的 session_id"

        # 验证：两个会话上下文独立
        assert execution1.session_id in mock_agent.session_context
        assert execution2.session_id in mock_agent.session_context
        assert len(mock_agent.session_context) == 2, "会话上下文数量不正确"

        print("\n[PASS] 不同任务隔离测试通过")
        print(f"   - 任务1 session_id: {execution1.session_id}")
        print(f"   - 任务2 session_id: {execution2.session_id}")
        print(f"   - 会话上下文独立: {list(mock_agent.session_context.keys())}")

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("运行定时任务上下文连续性测试...\n")
    asyncio.run(test_scheduled_task_context_continuity())
    asyncio.run(test_different_tasks_different_sessions())
