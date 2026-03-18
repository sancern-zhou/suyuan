"""
update_task 工具

允许LLM在ReAct循环中更新任务状态。
"""
import structlog
from typing import Dict, Any, Optional

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.agent.task.models import TaskStatus

logger = structlog.get_logger()


class UpdateTaskTool(LLMTool):
    """更新任务工具"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "update_task",
                "description": (
                    "更新任务状态。用于标记任务的执行进度。\n\n"
                    "使用场景：\n"
                    "- 开始执行任务时，标记为 in_progress\n"
                    "- 完成任务时，标记为 completed\n"
                    "- 任务失败时，标记为 failed\n\n"
                    "工作流程示例：\n"
                    "1. list_tasks() - 查看待执行任务\n"
                    "2. update_task(task_id='task_001', status='in_progress') - 开始执行\n"
                    "3. [执行具体操作，如调用get_weather_data]\n"
                    "4. update_task(task_id='task_001', status='completed') - 标记完成"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID，如'task_001'"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "failed"],
                            "description": (
                                "任务状态：\n"
                                "- pending: 待执行\n"
                                "- in_progress: 执行中\n"
                                "- completed: 已完成\n"
                                "- failed: 失败"
                            )
                        },
                        "progress": {
                            "type": "integer",
                            "description": "任务进度（0-100），可选",
                            "minimum": 0,
                            "maximum": 100
                        }
                    },
                    "required": ["task_id", "status"]
                }
            }
        }

        super().__init__(
            name="update_task",
            description="更新任务状态",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True  # ✅ 需要 ExecutionContext（用于获取 task_list）
        )
        # ✅ 标记需要 TaskList（不需要 DataContextManager）
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        task_id: str,
        status: str,
        progress: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行任务更新

        Args:
            context: 执行上下文
            task_id: 任务ID
            status: 任务状态
            progress: 任务进度

        Returns:
            更新结果
        """
        try:
            # 从context获取task_list
            task_list = context.get_task_list()

            # 验证任务是否存在
            task = task_list.get_task(task_id)
            if not task:
                return {
                    "status": "failed",
                    "success": False,
                    "data": {},
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "update_task"
                    },
                    "summary": f"任务不存在: {task_id}"
                }

            # 更新任务
            update_kwargs = {"status": TaskStatus(status)}
            if progress is not None:
                update_kwargs["progress"] = progress

            task_list.update_task(task_id, **update_kwargs)

            logger.info(
                f"Task updated by LLM: task_id={task_id}, "
                f"status={status}, progress={progress}"
            )

            # 获取更新后的任务
            updated_task = task_list.get_task(task_id)

            return {
                "status": "success",
                "success": True,
                "data": {
                    "task_id": updated_task.id,
                    "subject": updated_task.subject,
                    "status": updated_task.status.value,
                    "progress": updated_task.progress
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "update_task",
                    "field_mapping_applied": False
                },
                "summary": f"任务 {task_id} 已更新为 {status}"
            }

        except ValueError as e:
            logger.error(f"Invalid status value: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "update_task"
                },
                "summary": f"更新任务失败: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Failed to update task: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "update_task"
                },
                "summary": f"更新任务失败: {str(e)}"
            }


# 创建工具实例
update_task_tool = UpdateTaskTool()
