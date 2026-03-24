"""
ReAct Agent 扩展版本

集成任务管理和断点恢复功能。

使用方式：
    from app.agent.react_agent_extended import ReActAgentExtended

    agent = ReActAgentExtended(enable_task_planning=True)
    async for event in agent.analyze("综合分析广州O3污染溯源"):
        print(event)
"""

import structlog
from typing import Dict, Any, AsyncGenerator, Optional

from .react_agent import ReActAgent
from .task_planning_mixin import TaskPlanningMixin

logger = structlog.get_logger()


class ReActAgentExtended(ReActAgent, TaskPlanningMixin):
    """
    ReAct Agent 扩展版本

    在原有 ReAct Agent 基础上添加：
    1. 任务管理工具（create_task, update_task, list_tasks, get_task）
    2. 断点恢复（自动检测未完成任务）
    3. LLM 自主决策是否使用任务管理

    完全向后兼容，不影响现有功能。
    """

    def __init__(
        self,
        enable_task_planning: bool = True,  # 是否启用任务规划
        **kwargs
    ):
        """
        初始化扩展版 ReAct Agent

        Args:
            enable_task_planning: 是否启用任务规划功能
            **kwargs: 传递给 ReActAgent 的其他参数
        """
        # 初始化父类
        ReActAgent.__init__(self, **kwargs)
        TaskPlanningMixin.__init__(self)

        self.enable_task_planning = enable_task_planning

        # 将 task_list 传递给 executor
        self.executor.task_list = self.task_list

        logger.info(
            "react_agent_extended_initialized",
            enable_task_planning=enable_task_planning
        )

    async def analyze(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        分析用户查询（扩展版本）

        增强功能：
        1. 自动检测未完成的检查点并恢复
        2. LLM 可以在 ReAct 循环中使用任务管理工具
        3. 完全向后兼容

        Args:
            user_query: 用户查询
            session_id: 会话ID
            **kwargs: 其他参数

        Yields:
            流式事件
        """
        # 如果不启用任务规划，直接调用父类方法
        if not self.enable_task_planning:
            async for event in ReActAgent.analyze(
                self,
                user_query=user_query,
                session_id=session_id,
                **kwargs
            ):
                yield event
            return

        # ========================================
        # 启用任务规划模式
        # ========================================

        # 获取或创建会话
        actual_session_id, memory_manager, created_new = await self._get_or_create_session(
            session_id,
            reset_session=kwargs.get('reset_session', False)
        )

        # 更新 executor 的 memory_manager
        self.executor.set_memory_manager(memory_manager)

        logger.info(
            "analysis_started_with_task_management",
            session_id=actual_session_id,
            query=user_query[:100]
        )

        try:
            # ========================================
            # 1. 检查是否有未完成的检查点
            # ========================================
            checkpoint_manager = self._get_checkpoint_manager(actual_session_id)
            checkpoint_info = await self._check_and_restore_checkpoint(actual_session_id)

            if checkpoint_info:
                # 发送检查点恢复事件
                yield {
                    "type": "checkpoint_restored",
                    "data": {
                        "checkpoint_id": checkpoint_info["checkpoint_id"],
                        "message": f"从上次中断处恢复，已完成 {checkpoint_info['completed_tasks']} 个任务",
                        "completed_tasks": checkpoint_info["completed_tasks"],
                        "pending_tasks": checkpoint_info["pending_tasks"],
                        "in_progress_tasks": checkpoint_info["in_progress_tasks"]
                    }
                }

                # 继续执行未完成的任务
                async for event in self._execute_task_plan(
                    actual_session_id,
                    memory_manager,
                    checkpoint_manager
                ):
                    yield event

                return

            # ========================================
            # 2. 使用标准 ReAct 循环
            # LLM 自己决定是否使用任务管理工具
            # ========================================
            logger.info(
                f"Starting ReAct loop with task management tools available: "
                f"session_id={actual_session_id}"
            )

            async for event in ReActAgent.analyze(
                self,
                user_query=user_query,
                session_id=actual_session_id,
                **kwargs
            ):
                yield event

        except Exception as e:
            logger.error(
                f"Analysis with task management failed: {e}",
                exc_info=True
            )

            yield {
                "type": "fatal_error",
                "data": {
                    "error": str(e),
                    "session_id": actual_session_id
                }
            }

        finally:
            await self._mark_session_used(actual_session_id)


# 便捷函数：创建扩展版 Agent
def create_react_agent_extended(
    enable_task_planning: bool = True,
    **kwargs
) -> ReActAgentExtended:
    """
    创建扩展版 ReAct Agent

    Args:
        enable_task_planning: 是否启用任务规划
        **kwargs: 其他参数

    Returns:
        ReActAgentExtended 实例
    """
    return ReActAgentExtended(
        enable_task_planning=enable_task_planning,
        **kwargs
    )
