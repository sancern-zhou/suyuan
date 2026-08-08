"""
ReAct Agent Extended 简化集成测试

测试核心功能，不依赖复杂的Mock。
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.react_agent_extended import ReActAgentExtended, create_react_agent_extended
from app.agent.task.models import TaskStatus


class TestReActAgentExtendedBasic:
    """基础功能测试"""

    @pytest.mark.asyncio
    async def test_agent_creation(self):
        """测试Agent创建"""
        # 启用任务规划
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        assert agent is not None
        assert agent.enable_task_planning is True
        assert hasattr(agent, 'task_list')
        assert hasattr(agent, '_checkpoint_managers')

    @pytest.mark.asyncio
    async def test_agent_creation_disabled(self):
        """测试禁用任务规划的Agent创建"""
        agent = create_react_agent_extended(
            enable_task_planning=False,
            enable_multi_expert=False
        )

        assert agent is not None
        assert agent.enable_task_planning is False

    @pytest.mark.asyncio
    async def test_checkpoint_manager_creation(self):
        """测试检查点管理器创建"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        session_id = "test_session"
        checkpoint_manager = agent._get_checkpoint_manager(session_id)

        assert checkpoint_manager is not None
        assert checkpoint_manager.session_id == session_id

        # 再次获取应该返回同一个实例
        checkpoint_manager2 = agent._get_checkpoint_manager(session_id)
        assert checkpoint_manager is checkpoint_manager2

    @pytest.mark.asyncio
    async def test_task_list_shared(self):
        """测试任务列表在所有会话间共享"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        # 创建两个会话的检查点管理器
        cm1 = agent._get_checkpoint_manager("session_1")
        cm2 = agent._get_checkpoint_manager("session_2")

        # 应该共享同一个任务列表
        assert cm1.task_list is cm2.task_list
        assert cm1.task_list is agent.task_list

    @pytest.mark.asyncio
    async def test_check_no_checkpoint(self):
        """测试没有检查点的情况"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        session_id = "test_no_checkpoint"
        checkpoint_info = await agent._check_and_restore_checkpoint(session_id)

        # 应该返回None（没有检查点）
        assert checkpoint_info is None

    @pytest.mark.asyncio
    async def test_task_execution_with_mock(self):
        """测试任务执行（使用Mock）"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        # 手动创建一个任务
        session_id = "test_execution"
        task = agent.task_list.create_task(
            session_id=session_id,
            task_id="task_001",
            subject="测试任务",
            description="测试任务描述",
            depends_on=[],
            expert_type=None
        )

        # Mock _execute_task_with_react
        with patch.object(agent, '_execute_task_with_react') as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "data_id": "test_data",
                "answer": "任务完成"
            }

            # 执行任务
            checkpoint_manager = agent._get_checkpoint_manager(session_id)
            memory_manager = MagicMock()

            events = []
            async for event in agent._execute_task_plan(
                session_id,
                memory_manager,
                checkpoint_manager
            ):
                events.append(event)

            # 验证事件
            task_started = [e for e in events if e["type"] == "task_started"]
            assert len(task_started) == 1
            assert task_started[0]["data"]["task_id"] == "task_001"

            task_completed = [e for e in events if e["type"] == "task_completed"]
            assert len(task_completed) == 1

            all_completed = [e for e in events if e["type"] == "all_tasks_completed"]
            assert len(all_completed) == 1

            # 验证任务状态
            task = agent.task_list.get_task("task_001")
            assert task.status == TaskStatus.COMPLETED
            assert task.progress == 100

    @pytest.mark.asyncio
    async def test_task_dependency_order(self):
        """测试任务依赖顺序"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        session_id = "test_dependency"

        # 创建两个任务，task_002依赖task_001
        task1 = agent.task_list.create_task(
            session_id=session_id,
            task_id="task_001",
            subject="任务1",
            description="描述1",
            depends_on=[]
        )

        task2 = agent.task_list.create_task(
            session_id=session_id,
            task_id="task_002",
            subject="任务2",
            description="描述2",
            depends_on=["task_001"]
        )

        # 获取可执行任务
        ready_tasks = agent.task_list.get_ready_tasks(session_id)

        # 应该只有task_001可执行
        assert len(ready_tasks) == 1
        assert ready_tasks[0].id == "task_001"

        # 完成task_001
        agent.task_list.update_task("task_001", status=TaskStatus.COMPLETED)

        # 再次获取可执行任务
        ready_tasks = agent.task_list.get_ready_tasks(session_id)

        # 现在task_002应该可执行
        assert len(ready_tasks) == 1
        assert ready_tasks[0].id == "task_002"

    @pytest.mark.asyncio
    async def test_checkpoint_save_and_load(self):
        """测试检查点保存和加载"""
        agent = create_react_agent_extended(
            enable_task_planning=True,
            enable_multi_expert=False
        )

        session_id = "test_checkpoint"

        # 创建任务
        task = agent.task_list.create_task(
            session_id=session_id,
            task_id="task_001",
            subject="测试任务",
            description="测试描述",
            depends_on=[]
        )

        # 保存检查点
        checkpoint_manager = agent._get_checkpoint_manager(session_id)
        checkpoint_id = await checkpoint_manager.save_checkpoint("test")

        assert checkpoint_id is not None

        # 加载检查点
        checkpoint_data = await checkpoint_manager.load_checkpoint()

        assert checkpoint_data is not None
        assert checkpoint_data["checkpoint_id"] == checkpoint_id
        assert len(checkpoint_data["tasks"]) == 1
        assert checkpoint_data["tasks"][0]["id"] == "task_001"

        # 清空任务列表
        agent.task_list.clear_session_tasks(session_id)
        assert len(agent.task_list.get_tasks(session_id)) == 0

        # 恢复检查点
        success = await checkpoint_manager.restore_from_checkpoint()
        assert success is True

        # 验证任务已恢复
        restored_tasks = agent.task_list.get_tasks(session_id)
        assert len(restored_tasks) == 1
        assert restored_tasks[0].id == "task_001"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
