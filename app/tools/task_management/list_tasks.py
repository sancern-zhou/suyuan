"""
list_tasks 工具

允许LLM在ReAct循环中查看当前会话的任务清单。
"""
import structlog
from typing import Dict, Any, Optional

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class ListTasksTool(LLMTool):
    """列出任务工具"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": (
                    "查看当前会话的所有任务及其状态。用于了解任务清单的整体情况。\n\n"
                    "使用场景：\n"
                    "- 查看有哪些任务待执行\n"
                    "- 检查任务的依赖关系\n"
                    "- 决定下一步执行哪个任务\n"
                    "- 查看任务完成进度\n\n"
                    "返回信息包括：\n"
                    "- 任务ID、标题、描述\n"
                    "- 任务状态（pending/in_progress/completed/failed）\n"
                    "- 任务进度（0-100%）\n"
                    "- 依赖关系（depends_on）\n"
                    "- 是否可执行（ready）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

        super().__init__(
            name="list_tasks",
            description="查看当前会话的任务清单",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True  # ✅ 需要 ExecutionContext（用于获取 task_list）
        )
        # ✅ 标记需要 TaskList（不需要 DataContextManager）
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        执行任务列表查询

        Args:
            context: 执行上下文

        Returns:
            任务列表
        """
        try:
            # 从context获取task_list
            task_list = context.get_task_list()
            session_id = context.session_id

            # 获取所有任务
            tasks = task_list.get_tasks(session_id)

            # 获取可执行任务
            ready_tasks = task_list.get_ready_tasks(session_id)
            ready_task_ids = {t.id for t in ready_tasks}

            # 获取进度统计
            progress = task_list.get_session_progress(session_id)

            # 格式化任务列表
            task_data = []
            for task in tasks:
                task_data.append({
                    "task_id": task.id,
                    "subject": task.subject,
                    "description": task.description,
                    "status": task.status.value,
                    "progress": task.progress,
                    "depends_on": task.depends_on,
                    "ready": task.id in ready_task_ids,
                    "result_data_id": task.result_data_id
                })

            logger.info(
                f"Tasks listed by LLM: session_id={session_id}, "
                f"total={len(tasks)}, ready={len(ready_tasks)}"
            )

            # 生成摘要
            summary_parts = [
                f"当前有 {progress['total']} 个任务",
                f"已完成 {progress['completed']} 个",
                f"进行中 {progress['in_progress']} 个",
                f"待执行 {progress['pending']} 个"
            ]
            if progress['failed'] > 0:
                summary_parts.append(f"失败 {progress['failed']} 个")
            if len(ready_tasks) > 0:
                summary_parts.append(f"可执行 {len(ready_tasks)} 个")

            return {
                "status": "success",
                "success": True,
                "data": {
                    "tasks": task_data,
                    "progress": progress,
                    "ready_count": len(ready_tasks)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "list_tasks",
                    "field_mapping_applied": False,
                    "record_count": len(tasks)
                },
                "summary": "，".join(summary_parts)
            }

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {"tasks": [], "progress": {}},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "list_tasks"
                },
                "summary": f"查询任务列表失败: {str(e)}"
            }


# 创建工具实例
list_tasks_tool = ListTasksTool()
