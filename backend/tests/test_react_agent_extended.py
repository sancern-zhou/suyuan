"""
ReAct Agent Extended 集成测试

测试完整的任务规划和执行流程。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.react_agent_extended import ReActAgentExtended, create_react_agent_extended
from app.agent.task.models import TaskStatus


@pytest.fixture
def mock_llm_service():
    """模拟 LLM 服务"""
    mock = MagicMock()
    mock.chat = AsyncMock()
    return mock


@pytest.fixture
def agent_extended():
    """创建扩展版 Agent"""
    return create_react_agent_extended(
        enable_task_planning=True,
        enable_multi_expert=False  # 禁用多专家系统以简化测试
    )


class TestReActAgentExtended:
    """扩展版 ReAct Agent 测试类"""

    @pytest.mark.asyncio
    async def test_simple_query_no_task_plan(self, agent_extended, mock_llm_service):
        """测试简单查询不创建任务清单"""
        # Mock LLM 服务
        with patch('app.agent.core.task_planner.llm_service', mock_llm_service):
            # Mock 复杂度分析：简单查询
            mock_llm_service.chat.return_value = '{"needs_task_plan": false, "reason": "简单查询", "estimated_steps": 1, "complexity": "simple", "suggested_tasks": []}'

            # Mock ReAct 循环的响应
            with patch.object(agent_extended, '_execute_react_loop') as mock_react:
                mock_react.return_value = AsyncMock()

                events = []
                async for event in agent_extended.analyze(
                    user_query="查询PM2.5数据",
                    session_id="test_simple"
                ):
                    events.append(event)

                # 验证：不应该创建任务清单
                task_plan_events = [e for e in events if e["type"] == "task_plan_created"]
                assert len(task_plan_events) == 0

    @pytest.mark.asyncio
    async def test_complex_query_creates_task_plan(self, agent_extended, mock_llm_service):
        """测试复杂查询创建任务清单"""
        # Mock LLM 服务
        with patch('app.agent.core.task_planner.llm_service', mock_llm_service):
            # Mock 复杂度分析：复杂任务
            mock_llm_service.chat.side_effect = [
                '{"needs_task_plan": true, "reason": "复杂任务", "estimated_steps": 3, "complexity": "complex", "suggested_tasks": ["任务1", "任务2", "任务3"]}',
                '[{"task_id": "task_001", "subject": "任务1", "description": "描述1", "depends_on": [], "expert_type": null, "estimated_duration": 30}]'
            ]

            # Mock 任务执行
            with patch.object(agent_extended, '_execute_task_with_react') as mock_exec:
                mock_exec.return_value = {"success": True, "data_id": "test_data", "answer": "完成"}

                events = []
                async for event in agent_extended.analyze(
                    user_query="综合分析广州O3污染溯源",
                    session_id="test_complex"
                ):
                    events.append(event)

                # 验证：应该创建任务清单
                task_plan_events = [e for e in events if e["type"] == "task_plan_created"]
                assert len(task_plan_events) == 1
                assert task_plan_events[0]["data"]["task_count"] == 1

                # 验证：任务应该被执行
                task_started_events = [e for e in events if e["type"] == "task_started"]
                assert len(task_started_events) == 1

                task_completed_events = [e for e in events if e["type"] == "task_completed"]
                assert len(task_completed_events) == 1

    @pytest.mark.asyncio
    async def test_checkpoint_restore(self, agent_extended, mock_llm_service):
        """测试检查点恢复"""
        session_id = "test_checkpoint_restore"

        # Mock LLM 服务
        with patch('app.agent.core.task_planner.llm_service', mock_llm_service):
            # 第一次执行：创建任务清单
            mock_llm_service.chat.side_effect = [
                '{"needs_task_plan": true, "reason": "复杂任务", "estimated_steps": 2, "complexity": "complex", "suggested_tasks": ["任务1", "任务2"]}',
                '[{"task_id": "task_001", "subject": "任务1", "description": "描述1", "depends_on": [], "expert_type": null, "estimated_duration": 30}, {"task_id": "task_002", "subject": "任务2", "description": "描述2", "depends_on": ["task_001"], "expert_type": null, "estimated_duration": 30}]'
            ]

            # Mock 任务执行（第一个任务成功，第二个任务模拟中断）
            exec_count = 0

            async def mock_exec_side_effect(task, memory_manager):
                nonlocal exec_count
                exec_count += 1
                if exec_count == 1:
                    return {"success": True, "data_id": "test_data_1", "answer": "任务1完成"}
                else:
                    # 模拟中断
                    raise Exception("模拟中断")

            with patch.object(agent_extended, '_execute_task_with_react', side_effect=mock_exec_side_effect):
                events = []
                try:
                    async for event in agent_extended.analyze(
                        user_query="综合分析",
                        session_id=session_id
                    ):
                        events.append(event)
                except:
                    pass  # 忽略中断异常

                # 验证：第一个任务完成
                task_completed_events = [e for e in events if e["type"] == "task_completed"]
                assert len(task_completed_events) == 1

            # 第二次执行：恢复检查点
            with patch.object(agent_extended, '_execute_task_with_react') as mock_exec:
                mock_exec.return_value = {"success": True, "data_id": "test_data_2", "answer": "任务2完成"}

                events = []
                async for event in agent_extended.analyze(
                    user_query="继续执行",  # 查询内容不重要，会自动恢复
                    session_id=session_id
                ):
                    events.append(event)

                # 验证：应该恢复检查点
                checkpoint_restored_events = [e for e in events if e["type"] == "checkpoint_restored"]
                assert len(checkpoint_restored_events) == 1

                # 验证：第二个任务应该被执行
                task_completed_events = [e for e in events if e["type"] == "task_completed"]
                assert len(task_completed_events) == 1

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, agent_extended):
        """测试向后兼容性（禁用任务规划）"""
        # 创建禁用任务规划的 Agent
        agent_no_planning = create_react_agent_extended(
            enable_task_planning=False,
            enable_multi_expert=False
        )

        # Mock ReAct 循环
        with patch('app.agent.react_agent.ReActLoop') as mock_loop_class:
            mock_loop = MagicMock()
            mock_loop.run = AsyncMock()

            async def mock_run(*args, **kwargs):
                yield {"type": "complete", "data": {"answer": "测试答案"}}

            mock_loop.run.return_value = mock_run()
            mock_loop_class.return_value = mock_loop

            events = []
            async for event in agent_no_planning.analyze(
                user_query="测试查询",
                session_id="test_backward"
            ):
                events.append(event)

            # 验证：应该使用标准 ReAct 循环
            assert len(events) > 0
            # 不应该有任务规划相关事件
            task_plan_events = [e for e in events if e["type"] == "task_plan_created"]
            assert len(task_plan_events) == 0

    @pytest.mark.asyncio
    async def test_task_dependency_execution_order(self, agent_extended, mock_llm_service):
        """测试任务依赖关系的执行顺序"""
        # Mock LLM 服务
        with patch('app.agent.core.task_planner.llm_service', mock_llm_service):
            # Mock 任务清单：task_002 依赖 task_001
            mock_llm_service.chat.side_effect = [
                '{"needs_task_plan": true, "reason": "复杂任务", "estimated_steps": 2, "complexity": "complex", "suggested_tasks": ["任务1", "任务2"]}',
                '[{"task_id": "task_001", "subject": "任务1", "description": "描述1", "depends_on": [], "expert_type": null, "estimated_duration": 30}, {"task_id": "task_002", "subject": "任务2", "description": "描述2", "depends_on": ["task_001"], "expert_type": null, "estimated_duration": 30}]'
            ]

            # 记录执行顺序
            execution_order = []

            async def mock_exec_side_effect(task, memory_manager):
                execution_order.append(task.id)
                return {"success": True, "data_id": f"data_{task.id}", "answer": f"{task.subject}完成"}

            with patch.object(agent_extended, '_execute_task_with_react', side_effect=mock_exec_side_effect):
                events = []
                async for event in agent_extended.analyze(
                    user_query="综合分析",
                    session_id="test_dependency"
                ):
                    events.append(event)

                # 验证：执行顺序应该是 task_001 -> task_002
                assert execution_order == ["task_001", "task_002"]

    @pytest.mark.asyncio
    async def test_task_failure_handling(self, agent_extended, mock_llm_service):
        """测试任务失败处理"""
        # Mock LLM 服务
        with patch('app.agent.core.task_planner.llm_service', mock_llm_service):
            mock_llm_service.chat.side_effect = [
                '{"needs_task_plan": true, "reason": "复杂任务", "estimated_steps": 1, "complexity": "complex", "suggested_tasks": ["任务1"]}',
                '[{"task_id": "task_001", "subject": "任务1", "description": "描述1", "depends_on": [], "expert_type": null, "estimated_duration": 30}]'
            ]

            # Mock 任务执行失败
            with patch.object(agent_extended, '_execute_task_with_react') as mock_exec:
                mock_exec.side_effect = Exception("任务执行失败")

                events = []
                async for event in agent_extended.analyze(
                    user_query="综合分析",
                    session_id="test_failure"
                ):
                    events.append(event)

                # 验证：应该有任务失败事件
                task_failed_events = [e for e in events if e["type"] == "task_failed"]
                assert len(task_failed_events) == 1
                assert "任务执行失败" in task_failed_events[0]["data"]["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
