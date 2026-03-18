"""
测试定时任务上下文连续性

验证多步骤任务能够共享同一个 session_id，实现上下文连续
"""
import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from app.scheduled_tasks.models import ScheduledTask, TaskStep, ScheduleType
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
                    "summary": f"步骤完成，session_id={session_id}"
                },
                {"type": "data_saved", "data_id": data_id},
                {
                    "type": "final_response",
                    "content": f"已完成步骤，可访问的数据: {self.session_context[session_id]['data_ids']}"
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
    1. 整个任务使用统一的 session_id
    2. 所有步骤共享同一个 session_id
    3. 后续步骤能访问前面步骤生成的数据
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

        # 创建多步骤任务
        task = ScheduledTask(
            task_id="test_task_001",
            name="测试上下文连续性",
            description="验证多步骤任务的上下文连续性",
            schedule_type=ScheduleType.ONCE,
            steps=[
                TaskStep(
                    step_id="step_1",
                    description="第一步：查询数据",
                    agent_prompt="查询广州昨天的O3浓度数据",
                    timeout_seconds=60
                ),
                TaskStep(
                    step_id="step_2",
                    description="第二步：分析数据",
                    agent_prompt="基于上一步的数据，分析O3污染趋势",
                    timeout_seconds=120
                ),
                TaskStep(
                    step_id="step_3",
                    description="第三步：生成报告",
                    agent_prompt="基于前面的分析，生成综合报告",
                    timeout_seconds=180
                )
            ]
        )

        # 保存任务到存储（必须先保存，否则 execute_task 会在更新统计时找不到任务）
        task_storage.create(task)

        # 执行任务
        execution = await executor.execute_task(task)

        # 验证：任务执行成功
        assert execution.status.value == "success", f"任务执行失败: {execution.error_message}"
        assert execution.completed_steps == 3, f"完成步骤数不正确: {execution.completed_steps}"

        # 验证：任务有 session_id
        assert execution.session_id is not None, "任务未生成 session_id"
        assert execution.session_id.startswith("scheduled_task_"), f"session_id 格式不正确: {execution.session_id}"

        # 验证：所有步骤使用同一个 session_id
        assert len(mock_agent.analyze_calls) == 3, f"Agent 调用次数不正确: {len(mock_agent.analyze_calls)}"

        session_ids = [call["session_id"] for call in mock_agent.analyze_calls]
        assert len(set(session_ids)) == 1, f"步骤使用了不同的 session_id: {session_ids}"
        assert session_ids[0] == execution.session_id, "步骤的 session_id 与任务不一致"

        # 验证：上下文连续性（后续步骤能访问前面的数据）
        session_id = execution.session_id
        assert session_id in mock_agent.session_context, "会话上下文未创建"

        context_data = mock_agent.session_context[session_id]
        assert len(context_data["data_ids"]) == 3, f"上下文数据数量不正确: {context_data}"

        # 验证：步骤提示正确传递
        prompts = [call["prompt"] for call in mock_agent.analyze_calls]
        assert "查询广州昨天的O3浓度数据" in prompts[0]
        assert "基于上一步的数据" in prompts[1]
        assert "基于前面的分析" in prompts[2]

        print("\n[PASS] 上下文连续性测试通过")
        print(f"   - 任务 session_id: {execution.session_id}")
        print(f"   - 所有步骤共享同一个 session_id: {session_ids[0]}")
        print(f"   - 累积的数据 IDs: {context_data['data_ids']}")
        print(f"   - 步骤调用记录:")
        for i, call in enumerate(mock_agent.analyze_calls):
            print(f"     Step {i+1}: session_id={call['session_id'][:30]}..., prompt={call['prompt'][:50]}...")

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
            steps=[
                TaskStep(
                    step_id="step_1",
                    description="步骤1",
                    agent_prompt="执行任务1的步骤",
                    timeout_seconds=60
                )
            ]
        )

        # 创建第二个任务
        task2 = ScheduledTask(
            task_id="task_002",
            name="任务2",
            description="第二个任务",
            schedule_type=ScheduleType.ONCE,
            steps=[
                TaskStep(
                    step_id="step_1",
                    description="步骤1",
                    agent_prompt="执行任务2的步骤",
                    timeout_seconds=60
                )
            ]
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
