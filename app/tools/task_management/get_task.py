"""
get_task 工具

允许LLM在ReAct循环中获取特定任务的详细信息。
"""
import structlog
from typing import Dict, Any, Optional

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class GetTaskTool(LLMTool):
    """获取任务详情工具"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "get_task",
                "description": (
                    "获取特定任务的详细信息。用于查看任务的完整内容和执行结果。\n\n"
                    "使用场景：\n"
                    "- 查看任务的详细描述和要求\n"
                    "- 获取任务的执行结果（result_data_id）\n"
                    "- 检查任务的依赖关系\n"
                    "- 查看任务的错误信息（如果失败）\n\n"
                    "返回信息包括：\n"
                    "- 任务的完整描述\n"
                    "- 任务状态和进度\n"
                    "- 依赖的任务列表\n"
                    "- 执行结果的data_id（可用于后续分析）\n"
                    "- 错误信息（如果失败）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID，如'task_001'"
                        }
                    },
                    "required": ["task_id"]
                }
            }
        }

        super().__init__(
            name="get_task",
            description="获取任务详细信息",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True  # ✅ 需要 ExecutionContext（用于获取 task_list）
        )
        # ✅ 标记需要 TaskList（不需要 DataContextManager）
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        task_id: str
    ) -> Dict[str, Any]:
        """
        执行任务详情查询

        Args:
            context: 执行上下文
            task_id: 任务ID

        Returns:
            任务详情
        """
        try:
            # 从context获取task_list
            task_list = context.get_task_list()

            # 获取任务
            task = task_list.get_task(task_id)

            if not task:
                return {
                    "status": "failed",
                    "success": False,
                    "data": {},
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "get_task"
                    },
                    "summary": f"任务不存在: {task_id}"
                }

            logger.info(f"Task retrieved by LLM: task_id={task_id}")

            # 格式化任务详情
            task_detail = {
                "task_id": task.id,
                "subject": task.subject,
                "description": task.description,
                "status": task.status.value,
                "progress": task.progress,
                "depends_on": task.depends_on,
                "expert_type": task.expert_type,
                "result_data_id": task.result_data_id,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "metadata": task.metadata
            }

            return {
                "status": "success",
                "success": True,
                "data": task_detail,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_task",
                    "field_mapping_applied": False
                },
                "summary": f"任务详情: {task.subject} ({task.status.value})"
            }

        except Exception as e:
            logger.error(f"Failed to get task: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_task"
                },
                "summary": f"获取任务详情失败: {str(e)}"
            }


# 创建工具实例
get_task_tool = GetTaskTool()
