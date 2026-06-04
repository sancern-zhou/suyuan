"""
定时任务执行器
负责执行任务步骤，与ReAct Agent集成
"""
import asyncio
import structlog
from datetime import datetime
from typing import Optional
from uuid import uuid4

from ..models.task import ScheduledTask
from ..models.execution import (
    TaskExecution,
    StepExecution,
    ExecutionStatus
)
from ..storage import TaskStorage, ExecutionStorage

logger = structlog.get_logger()


class ScheduledTaskExecutor:
    """定时任务执行器"""

    def __init__(
        self,
        task_storage: TaskStorage,
        execution_storage: ExecutionStorage,
        agent_factory: Optional[callable] = None
    ):
        self.task_storage = task_storage
        self.execution_storage = execution_storage
        self.agent_factory = agent_factory  # 用于创建ReAct Agent实例

    async def execute_task(self, task: ScheduledTask) -> TaskExecution:
        """执行任务"""
        # 为整个任务创建统一的 session_id（保持所有步骤的上下文连续）
        task_session_id = self._generate_session_id(task.task_id)

        # 创建执行记录
        execution = TaskExecution(
            execution_id=self._generate_execution_id(task.task_id),
            task_id=task.task_id,
            task_name=task.name,
            session_id=task_session_id,  # ✅ 保存 session_id
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(),
            total_steps=len(task.steps),
            scheduled_time=task.next_run_at
        )

        # 保存执行记录
        self.execution_storage.create(execution)
        logger.info(
            f"Started execution: {execution.execution_id} for task: {task.name}, "
            f"session_id: {task_session_id}"
        )

        try:
            # 顺序执行步骤（所有步骤共享同一个 session_id）
            for i, step in enumerate(task.steps):
                execution.current_step_index = i
                self.execution_storage.update(execution)

                # 执行步骤（传入 session_id 以保持上下文连续）
                step_result = await self._execute_step(step, execution, task_session_id)
                execution.steps.append(step_result)

                # 更新统计
                if step_result.status == ExecutionStatus.SUCCESS:
                    execution.completed_steps += 1
                elif step_result.status == ExecutionStatus.FAILED:
                    execution.failed_steps += 1

                    # 如果步骤失败且不重试，终止任务
                    if not step.retry_on_failure:
                        logger.warning(
                            f"Step {step.step_id} failed and retry_on_failure=False, "
                            f"stopping task execution"
                        )
                        execution.status = ExecutionStatus.FAILED
                        execution.error_message = f"Step {step.step_id} failed: {step_result.error_message}"
                        break

                # 保存中间状态
                self.execution_storage.update(execution)

            # 任务完成
            if execution.status == ExecutionStatus.RUNNING:
                execution.status = ExecutionStatus.SUCCESS

        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)

        finally:
            # 完成执行
            execution.completed_at = datetime.now()
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()

            # 保存最终状态
            self.execution_storage.update(execution)

            # 更新任务统计
            self.task_storage.update_run_stats(
                task_id=task.task_id,
                success=(execution.status == ExecutionStatus.SUCCESS),
                next_run_at=None  # 由调度器更新
            )

            logger.info(
                f"Execution completed: {execution.execution_id}, "
                f"status: {execution.status}, "
                f"duration: {execution.duration_seconds:.2f}s"
            )

        return execution

    async def _execute_step(
        self,
        step,
        execution: TaskExecution,
        session_id: str  # ✅ 接收 session_id 参数
    ) -> StepExecution:
        """执行单个步骤"""
        step_exec = StepExecution(
            step_id=step.step_id,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(),
            agent_prompt=step.agent_prompt
        )

        logger.info(
            f"Executing step: {step.step_id} - {step.description}, "
            f"session_id: {session_id}"
        )

        try:
            # 执行步骤（带超时，并传入 session_id）
            result = await asyncio.wait_for(
                self._run_agent_step(step.agent_prompt, session_id),
                timeout=step.timeout_seconds
            )

            # 处理结果
            step_exec.status = ExecutionStatus.SUCCESS
            step_exec.agent_response = result.get("summary", "")
            step_exec.result_data_ids = result.get("data_ids", [])
            step_exec.result_visuals = result.get("visuals", [])
            step_exec.agent_thoughts = result.get("thoughts", [])
            step_exec.tool_calls = result.get("tool_calls", [])
            step_exec.iterations = result.get("iterations", 0)

            logger.info(f"Step {step.step_id} completed successfully")

        except asyncio.TimeoutError:
            step_exec.status = ExecutionStatus.TIMEOUT
            step_exec.error_message = f"Step timeout after {step.timeout_seconds}s"
            step_exec.error_type = "TimeoutError"
            logger.error(f"Step {step.step_id} timeout")

        except Exception as e:
            step_exec.status = ExecutionStatus.FAILED
            step_exec.error_message = str(e)
            step_exec.error_type = type(e).__name__
            logger.error(f"Step {step.step_id} failed: {e}", exc_info=True)

        finally:
            step_exec.completed_at = datetime.now()
            step_exec.duration_seconds = (
                step_exec.completed_at - step_exec.started_at
            ).total_seconds()

        return step_exec

    async def _run_agent_step(self, prompt: str, session_id: str) -> dict:
        """
        运行Agent步骤

        Args:
            prompt: Agent提示词
            session_id: 会话ID（保持整个任务的上下文连续）

        Returns:
            包含执行结果的字典
        """
        if not self.agent_factory:
            raise RuntimeError("Agent factory not configured")

        # 创建Agent实例
        agent = self.agent_factory()

        logger.info(
            f"Running agent step with session_id: {session_id}, "
            f"prompt: {prompt[:100]}..."
        )

        # 收集Agent响应
        data_ids = []
        visuals = []
        summary_parts = []
        thoughts = []
        tool_calls = []
        iterations = 0

        # ✅ 执行Agent分析，传入 session_id 以复用上下文
        async for event in agent.analyze(prompt, session_id=session_id):
            event_type = event.get("type")

            # 记录思考过程
            if event_type == "thought":
                thought = event.get("content", "")
                if thought:
                    thoughts.append(thought)

            # 记录工具调用
            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "")
                tool_args = event.get("args", {})
                tool_calls.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "timestamp": datetime.now().isoformat()
                })

            # 记录工具结果
            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "")
                success = event.get("success", False)
                summary = event.get("summary", "")
                # 将结果添加到最后一个工具调用
                if tool_calls:
                    tool_calls[-1]["success"] = success
                    tool_calls[-1]["result"] = summary

            # 记录迭代
            elif event_type == "iteration":
                iterations = event.get("iteration", 0)

            # 数据保存
            elif event_type == "data_saved":
                data_id = event.get("data_id")
                if data_id:
                    data_ids.append(data_id)

            # 可视化生成
            elif event_type == "visual_generated":
                visual = event.get("visual")
                if visual:
                    visuals.append(visual)

            elif event_type == "final_response":
                summary_parts.append(event.get("content", ""))

        return {
            "summary": "\n".join(summary_parts),
            "data_ids": data_ids,
            "visuals": visuals,
            "thoughts": thoughts,
            "tool_calls": tool_calls,
            "iterations": iterations
        }

    def _generate_execution_id(self, task_id: str) -> str:
        """生成执行ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid4())[:8]
        return f"exec_{task_id}_{timestamp}_{short_uuid}"

    def _generate_session_id(self, task_id: str) -> str:
        """
        生成会话ID（用于 ReAct Agent 上下文管理）

        Args:
            task_id: 任务ID

        Returns:
            格式: scheduled_task_{task_id}_{timestamp}_{uuid}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid4())[:8]
        return f"scheduled_task_{task_id}_{timestamp}_{short_uuid}"
