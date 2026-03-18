"""
ReAct Agent 任务规划扩展

为 ReAct Agent 添加自动任务规划和断点恢复功能。

核心功能：
1. 自动检测是否有未完成的检查点
2. 自动判断是否需要任务清单
3. 任务执行循环
4. 断点恢复
5. 与现有 ReAct 循环无缝集成
"""

import structlog
from typing import Dict, Any, AsyncGenerator, Optional, List

from app.agent.task.task_list import TaskList
from app.agent.task.checkpoint_manager import TaskCheckpointManager
from app.agent.task.models import Task, TaskStatus

logger = structlog.get_logger()


class TaskPlanningMixin:
    """
    任务规划混入类

    为 ReAct Agent 添加任务规划功能，不破坏现有架构。
    """

    def __init__(self):
        """初始化任务规划组件"""
        # 全局任务列表（所有会话共享）
        self.task_list = TaskList()

        # 会话级别的检查点管理器缓存
        self._checkpoint_managers: Dict[str, TaskCheckpointManager] = {}

        logger.info("TaskPlanningMixin initialized")

    def _get_checkpoint_manager(self, session_id: str) -> TaskCheckpointManager:
        """
        获取或创建检查点管理器

        Args:
            session_id: 会话ID

        Returns:
            检查点管理器实例
        """
        if session_id not in self._checkpoint_managers:
            self._checkpoint_managers[session_id] = TaskCheckpointManager(
                session_id=session_id,
                task_list=self.task_list
            )

        return self._checkpoint_managers[session_id]

    async def _check_and_restore_checkpoint(
        self,
        session_id: str
    ) -> Optional[Dict]:
        """
        检查并恢复检查点

        Args:
            session_id: 会话ID

        Returns:
            检查点信息，如果没有未完成的任务返回 None
        """
        try:
            checkpoint_manager = self._get_checkpoint_manager(session_id)

            # 检查是否有未完成的任务
            if not await checkpoint_manager.has_unfinished_tasks():
                return None

            # 获取检查点信息
            checkpoint_info = await checkpoint_manager.get_checkpoint_info()

            if not checkpoint_info:
                return None

            # 恢复检查点
            success = await checkpoint_manager.restore_from_checkpoint()

            if not success:
                logger.error(f"Failed to restore checkpoint for session {session_id}")
                return None

            logger.info(
                f"Checkpoint restored: session_id={session_id}, "
                f"checkpoint_id={checkpoint_info['checkpoint_id']}, "
                f"completed={checkpoint_info['completed_tasks']}, "
                f"pending={checkpoint_info['pending_tasks']}"
            )

            return checkpoint_info

        except Exception as e:
            logger.error(f"Failed to check and restore checkpoint: {e}", exc_info=True)
            return None

    async def _execute_task_plan(
        self,
        session_id: str,
        memory_manager,
        checkpoint_manager: TaskCheckpointManager
    ) -> AsyncGenerator[Dict, None]:
        """
        执行任务清单

        Args:
            session_id: 会话ID
            memory_manager: 记忆管理器
            checkpoint_manager: 检查点管理器

        Yields:
            任务执行事件
        """
        try:
            while True:
                # 获取可执行的任务
                ready_tasks = self.task_list.get_ready_tasks(session_id)

                if not ready_tasks:
                    # 所有任务完成
                    logger.info(f"All tasks completed for session {session_id}")
                    break

                for task in ready_tasks:
                    # ========================================
                    # 任务开始
                    # ========================================
                    logger.info(
                        f"Task started: task_id={task.id}, subject={task.subject}"
                    )

                    # 更新任务状态
                    self.task_list.update_task(
                        task.id,
                        status=TaskStatus.IN_PROGRESS
                    )

                    # 发送任务开始事件
                    yield {
                        "type": "task_started",
                        "data": {
                            "task_id": task.id,
                            "subject": task.subject,
                            "description": task.description,
                            "expert_type": task.expert_type
                        }
                    }

                    # 保存检查点
                    await checkpoint_manager.save_checkpoint("before_task")

                    # ========================================
                    # 执行任务
                    # ========================================
                    try:
                        # 根据专家类型执行
                        if task.expert_type and self.enable_multi_expert:
                            # 使用专家系统
                            result = await self._execute_task_with_expert(
                                task,
                                memory_manager
                            )
                        else:
                            # 使用普通 ReAct 循环
                            result = await self._execute_task_with_react(
                                task,
                                memory_manager
                            )

                        # 任务完成
                        self.task_list.update_task(
                            task.id,
                            status=TaskStatus.COMPLETED,
                            progress=100,
                            result_data_id=result.get("data_id")
                        )

                        # 发送任务完成事件
                        yield {
                            "type": "task_completed",
                            "data": {
                                "task_id": task.id,
                                "subject": task.subject,
                                "result": result
                            }
                        }

                    except Exception as e:
                        # 任务失败
                        logger.error(
                            f"Task failed: task_id={task.id}, error={str(e)}",
                            exc_info=True
                        )

                        self.task_list.update_task(
                            task.id,
                            status=TaskStatus.FAILED,
                            error_message=str(e)
                        )

                        yield {
                            "type": "task_failed",
                            "data": {
                                "task_id": task.id,
                                "subject": task.subject,
                                "error": str(e)
                            }
                        }

                    # 保存检查点
                    await checkpoint_manager.save_checkpoint("after_task")

            # ========================================
            # 所有任务完成
            # ========================================
            progress = self.task_list.get_session_progress(session_id)

            yield {
                "type": "all_tasks_completed",
                "data": {
                    "message": "所有任务已完成",
                    "progress": progress
                }
            }

        except Exception as e:
            logger.error(f"Task plan execution failed: {e}", exc_info=True)
            yield {
                "type": "task_plan_error",
                "data": {
                    "error": str(e)
                }
            }

    async def _execute_task_with_expert(
        self,
        task: Task,
        memory_manager
    ) -> Dict:
        """
        使用专家系统执行任务

        Args:
            task: 任务对象
            memory_manager: 记忆管理器

        Returns:
            执行结果
        """
        try:
            # 获取专家路由器
            expert_router = self._get_expert_router(memory_manager)

            if not expert_router:
                raise ValueError("Expert router not available")

            # 构造专家查询
            expert_query = f"{task.subject}: {task.description}"

            # 执行专家分析
            pipeline_result = await expert_router.execute_pipeline(
                expert_query,
                precision='standard'
            )

            # 转换结果
            result = {
                "success": pipeline_result.status in ["success", "partial"],
                "data_id": pipeline_result.data_ids[0] if pipeline_result.data_ids else None,
                "answer": pipeline_result.final_answer,
                "expert_type": task.expert_type
            }

            return result

        except Exception as e:
            logger.error(f"Expert execution failed: {e}", exc_info=True)
            raise

    async def _execute_task_with_react(
        self,
        task: Task,
        memory_manager
    ) -> Dict:
        """
        使用普通 ReAct 循环执行任务

        Args:
            task: 任务对象
            memory_manager: 记忆管理器

        Returns:
            执行结果
        """
        try:
            from .core.loop import ReActLoop

            # 创建 ReAct 循环
            react_loop = ReActLoop(
                memory_manager=memory_manager,
                llm_planner=self.planner,
                tool_executor=self.executor,
                max_iterations=5,  # 单个任务最多5次迭代
                stream_enabled=False  # 不流式输出
            )

            # 构造查询
            query = f"{task.subject}: {task.description}"

            # 执行 ReAct 循环
            final_answer = None
            data_id = None

            async for event in react_loop.run(
                user_query=query,
                enhance_with_history=False
            ):
                if event["type"] == "complete":
                    final_answer = event["data"].get("answer")
                    data_id = event["data"].get("data_id")
                    break
                elif event["type"] == "incomplete":
                    final_answer = event["data"].get("answer")
                    break

            result = {
                "success": final_answer is not None,
                "data_id": data_id,
                "answer": final_answer or "任务执行未获得结果"
            }

            return result

        except Exception as e:
            logger.error(f"ReAct execution failed: {e}", exc_info=True)
            raise
