"""
定时任务执行器
负责执行任务步骤，与ReAct Agent集成
"""
import asyncio
import json
import structlog
from datetime import datetime
from typing import Optional
from uuid import uuid4

from ..models.task import ScheduledTask
from ..models.event import TaskEvent
from ..models.execution import (
    TaskExecution,
    StepExecution,
    ExecutionStatus
)
from ..storage import TaskStorage, ExecutionStorage
from ..conversation_persistence import ScheduledTaskConversationPersistence

logger = structlog.get_logger()

# 与 event_bus._sanitize_result 的日志截断上限保持一致量级：事件上下文超限时
# 仅保留摘要与文件路径字段，完整证据必须通过持久化文件传递。
EVENT_CONTEXT_MAX_CHARS = 8000
_COMPACT_VALUE_MAX_CHARS = 200
_COMPACT_CONTAINER_MAX_CHARS = 400


def _is_path_like(value: str) -> bool:
    return "/" in value or "\\" in value


def _compact_value(value):
    """Shrink one payload entry: keep scalars, paths and short containers."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= _COMPACT_VALUE_MAX_CHARS or _is_path_like(value):
            return value
        return value[:_COMPACT_VALUE_MAX_CHARS] + "…<已截断>"
    if isinstance(value, list):
        if len(json.dumps(value, ensure_ascii=False, default=str)) <= _COMPACT_CONTAINER_MAX_CHARS:
            return value
        return f"<列表共 {len(value)} 项，已省略>"
    if isinstance(value, dict):
        if len(json.dumps(value, ensure_ascii=False, default=str)) <= _COMPACT_CONTAINER_MAX_CHARS:
            return value
        return {key: _compact_value(item) for key, item in value.items()}
    return str(value)


def _render_event_context(event) -> str:
    """Render trusted event context, compacting oversized payloads."""
    data = event.model_dump(mode="json")
    rendered = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(rendered) <= EVENT_CONTEXT_MAX_CHARS:
        return f"## 可信事件上下文\n{rendered}"
    note = (
        "注意：该事件 payload 过大，以上仅保留摘要、计数与文件路径等关键字段，"
        "超长字符串与大型列表已省略；完整证据必须通过 payload 中给出的文件路径"
        "（如 evidence_package_path）读取，不得凭空补写被省略的内容。"
    )
    data["payload"] = {key: _compact_value(value) for key, value in data.get("payload", {}).items()}
    rendered = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(rendered) > EVENT_CONTEXT_MAX_CHARS:
        data["payload"] = "<payload 过大，已整体省略，请使用事件关联的持久化文件>"
        rendered = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return f"## 可信事件上下文\n{rendered}\n\n{note}"


def build_runtime_custom_tool_registry(tool_names):
    """Validate and freeze the selected global tools for one custom task run."""
    from app.agent.tool_adapter import get_react_agent_tool_registry
    from app.services.lifecycle_manager import get_tool_registry
    from ..custom_agent import build_custom_tool_registry

    return build_custom_tool_registry(
        tool_names,
        get_tool_registry(),
        get_react_agent_tool_registry(),
    )


class ScheduledTaskExecutor:
    """定时任务执行器"""

    def __init__(
        self,
        task_storage: TaskStorage,
        execution_storage: ExecutionStorage,
        agent_factory: Optional[callable] = None,
        conversation_persistence=None,
    ):
        self.task_storage = task_storage
        self.execution_storage = execution_storage
        self.agent_factory = agent_factory  # 用于创建ReAct Agent实例
        self.conversation_persistence = (
            conversation_persistence or ScheduledTaskConversationPersistence()
        )
        self._persisted_execution_ids: set[str] = set()

    async def execute_task(
        self,
        task: ScheduledTask,
        event: TaskEvent | None = None,
        update_stats: bool = True,
        broadcast_user_names: list[str] | None = None,
    ) -> TaskExecution:
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
            total_steps=len(task.steps) or 1,
            scheduled_time=task.next_run_at if event is None else None,
            trigger_type="event" if event else "scheduled",
            event_id=event.event_id if event else None,
            event_type=event.event_type if event else None,
            event_attributes=event.attributes if event else {},
        )

        # 保存执行记录
        self.execution_storage.create(execution)
        logger.info(
            f"Started execution: {execution.execution_id} for task: {task.name}, "
            f"session_id: {task_session_id}"
        )

        try:
            shared_agent = None
            if task.execution_mode == "custom":
                if not self.agent_factory:
                    raise RuntimeError("Agent factory not configured")
                runtime_tool_names = list(task.tool_names or [])
                if task.broadcast_enabled and "broadcast_social_users" not in runtime_tool_names:
                    runtime_tool_names.append("broadcast_social_users")
                fixed_tools = build_runtime_custom_tool_registry(runtime_tool_names)
                shared_agent = self.agent_factory(
                    tool_registry=fixed_tools,
                    enable_memory=False,
                )

            configured_steps = task.steps
            prompts = configured_steps or [None]
            for index, configured_step in enumerate(prompts):
                execution.current_step_index = index
                self.execution_storage.update(execution)
                prompt = self._build_task_prompt(
                    configured_step.agent_prompt if configured_step else task.prompt,
                    task=task,
                    event=event,
                    execution_id=execution.execution_id,
                    broadcast_user_names=broadcast_user_names,
                )
                result = await asyncio.wait_for(
                    self._run_agent(
                        prompt, task_session_id,
                        manual_mode=task.execution_mode,
                        task=task, execution=execution, agent=shared_agent,
                    ),
                    timeout=(configured_step.timeout_seconds if configured_step else task.timeout_seconds),
                )
                execution.steps.append(self._result_to_execution(
                    result, prompt, configured_step.step_id if configured_step else "task"
                ))
                execution.completed_steps += 1
            self.execution_storage.update(execution)

            # 任务完成
            if execution.status == ExecutionStatus.RUNNING:
                execution.status = ExecutionStatus.SUCCESS

        except asyncio.TimeoutError:
            execution.status = ExecutionStatus.TIMEOUT
            execution.error_message = f"Task timeout after {task.timeout_seconds}s"
            logger.error(
                "scheduled_task_timeout",
                task_id=task.task_id,
                timeout_seconds=task.timeout_seconds,
            )
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

            try:
                if execution.execution_id not in self._persisted_execution_ids:
                    await self.conversation_persistence.ensure_terminal_session(
                        task=task,
                        execution=execution,
                    )
                if execution.execution_id in self._persisted_execution_ids or execution.session_id:
                    await self.conversation_persistence.publish_conversation(
                        task=task,
                        execution=execution,
                    )
            except Exception as publish_error:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = (
                    f"Scheduled conversation publication failed: {publish_error}"
                )
            finally:
                self._persisted_execution_ids.discard(execution.execution_id)

            # 保存最终状态
            self.execution_storage.update(execution)

            # 更新任务统计
            if update_stats:
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

    def _result_to_execution(self, result: dict, prompt: str, step_id: str = "task") -> StepExecution:
        return StepExecution(
            step_id=step_id,
            status=ExecutionStatus.SUCCESS,
            agent_prompt=prompt,
            agent_response=result.get("summary", ""),
            result_data_ids=result.get("data_ids", []),
            result_visuals=result.get("visuals", []),
            agent_thoughts=result.get("thoughts", []),
            tool_calls=result.get("tool_calls", []),
            iterations=result.get("iterations", 0),
        )

    async def _run_agent(
        self,
        prompt: str,
        session_id: str,
        manual_mode: str,
        task: ScheduledTask | None = None,
        execution: TaskExecution | None = None,
        agent=None,
    ) -> dict:
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

        # custom 模式由任务执行器创建一个固定工具集的 Agent 并在所有步骤间复用。
        agent = agent or self.agent_factory()

        selected_skill_context = None
        if task is not None and task.skill_id:
            from app.agent.selection_context import load_skill_selection

            selection = load_skill_selection(task.skill_id)
            selected_skill_context = selection.content

        logger.info(
            f"Running agent step with session_id: {session_id}, "
            f"prompt: {prompt[:100]}..."
        )

        knowledge_base_ids = None
        if task is not None and task.knowledge_base_binding:
            from app.knowledge_base.project_bindings import resolve_project_knowledge_base_ids

            knowledge_base_ids = await resolve_project_knowledge_base_ids(
                task.knowledge_base_binding
            )
            if not knowledge_base_ids:
                logger.warning(
                    "scheduled_task_knowledge_base_unavailable",
                    task_id=task.task_id,
                    binding=task.knowledge_base_binding,
                )

        # 收集Agent响应
        data_ids = []
        visuals = []
        summary_parts = []
        thoughts = []
        tool_calls = []
        iterations = 0
        display_history = [{
            "type": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat(),
        }]

        # ✅ 执行Agent分析，传入 session_id 以复用上下文
        try:
            async for event in agent.analyze(
                prompt,
                session_id=session_id,
                manual_mode=manual_mode,
                session_storage_mode=("custom" if manual_mode == "custom" else "assistant"),
                selected_skill_context=selected_skill_context,
                knowledge_base_ids=knowledge_base_ids,
            ):
                event_type = event.get("type")
                event_data = event.get("data") if isinstance(event.get("data"), dict) else {}

                if event_type in {"thought", "tool_use", "tool_result"}:
                    frontend_message = {
                        "type": event_type,
                        "data": event_data,
                        "timestamp": event_data.get("timestamp") or datetime.now().isoformat(),
                    }
                    if event_type == "thought":
                        frontend_message["content"] = event_data.get("thought") or event.get("content", "")
                    elif event_type == "tool_use":
                        tool_name = event_data.get("tool_name") or event.get("tool_name", "")
                        frontend_message["content"] = f"调用工具: {tool_name}" if tool_name else "执行行动"
                    else:
                        result = event_data.get("result")
                        if isinstance(result, dict):
                            frontend_message["content"] = result.get("summary_text") or result.get("summary") or "获得结果"
                        else:
                            frontend_message["content"] = str(result or event.get("summary") or "获得结果")
                    display_history.append(frontend_message)

                # 记录思考过程
                if event_type == "thought":
                    thought = event_data.get("thought") or event.get("content", "")
                    if thought:
                        thoughts.append(thought)

                # 记录工具调用
                elif event_type in {"tool_call", "tool_use"}:
                    tool_name = event_data.get("tool_name") or event.get("tool_name", "")
                    tool_args = event_data.get("input") or event.get("args", {})
                    tool_calls.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "timestamp": datetime.now().isoformat()
                    })

                # 记录工具结果
                elif event_type == "tool_result":
                    result = event_data.get("result")
                    if tool_calls:
                        tool_calls[-1]["success"] = not event_data.get("is_error", False)
                        tool_calls[-1]["result"] = result or event.get("summary", "")

                elif event_type == "iteration":
                    iterations = event.get("iteration", 0)
                elif event_type == "data_saved":
                    data_id = event.get("data_id")
                    if data_id:
                        data_ids.append(data_id)
                elif event_type == "visual_generated":
                    visual = event.get("visual")
                    if visual:
                        visuals.append(visual)
                elif event_type == "final_response":
                    summary_parts[:] = [event.get("content", "")]
                elif event_type == "agent_finish":
                    summary_parts[:] = [event.get("answer") or event_data.get("answer", "")]
                elif event_type == "complete":
                    data = event.get("data") or {}
                    summary_parts[:] = [data.get("answer") or data.get("response") or ""]
                elif event_type == "fatal_error":
                    error = event_data.get("error") or event.get("error") or "Agent execution failed"
                    raise RuntimeError(error)
        except BaseException as analysis_error:
            display_history.append({
                "type": "error",
                "content": str(analysis_error) or type(analysis_error).__name__,
                "timestamp": datetime.now().isoformat(),
            })
            raise
        finally:
            final_answer = "\n".join(summary_parts)
            if final_answer:
                display_history.append({
                    "type": "final",
                    "role": "assistant",
                    "content": final_answer,
                    "data": {"answer": final_answer},
                    "timestamp": datetime.now().isoformat(),
                })
            if task is not None and execution is not None:
                persisted = await self.conversation_persistence.persist_agent_session(
                    agent=agent,
                    task=task,
                    execution=execution,
                    display_history=display_history,
                )
                if persisted:
                    self._persisted_execution_ids.add(execution.execution_id)

        return {
            "summary": "\n".join(summary_parts),
            "data_ids": data_ids,
            "visuals": visuals,
            "thoughts": thoughts,
            "tool_calls": tool_calls,
            "iterations": iterations
        }

    @staticmethod
    def _build_task_prompt(
        prompt: str,
        task: ScheduledTask,
        event: TaskEvent | None = None,
        execution_id: str | None = None,
        broadcast_user_names: list[str] | None = None,
    ) -> str:
        sections = [prompt]
        if event is not None:
            sections.append(_render_event_context(event))
        if execution_id:
            sections.append(
                "## 本次执行标识\n"
                f"execution_id: {execution_id}\n"
                "本次执行生成的报告包 ID 必须包含此 execution_id；同一事件的重试必须生成独立报告，"
                "不得覆盖其他执行已经生成的报告文件。"
            )
        if task.broadcast_enabled:
            names = ", ".join(broadcast_user_names or [])
            sections.append(
                """## 输出与投递约束
- 完成任务后调用 `broadcast_social_users` 发送结果。
- 目标微信用户名称：%s
- `target_user_names` 使用上述名称；生成的附件必须使用上游工具返回的最终成品路径（例如 render_report_package 的 `path` 或 resources 中的 DOCX/PDF），禁止把 `report.qmd`/`file_path` 源文件当作正式报告附件，也禁止自行拼接路径。
- 广播工具执行完成后，正常简要说明执行结果，不需要返回 JSON。""" % names
            )
        return "\n\n".join(sections)

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
