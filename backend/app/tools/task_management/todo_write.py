"""
TodoWrite Tool - Simple task management tool

Replaces the 4-tool task management system with a single complete-replacement tool.

Key improvements:
- Single tool instead of 4 (create_task, update_task, list_tasks, get_task)
- 2 fields instead of 15+ (content, status)
- Complete replacement mode instead of incremental updates
- Constraints: max 20 items, one in_progress at a time
- Simple text rendering output

Usage example:
    TodoWrite(items=[
        {"content": "读取Excel文件", "status": "completed"},
        {"content": "分析数据", "status": "in_progress"},
        {"content": "生成报告", "status": "pending"}
    ])
"""

import structlog
from typing import Dict, Any, List

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class TodoWriteTool(LLMTool):
    """TodoWrite tool for simple task management"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "TodoWrite",
                "description": (
                    "更新任务清单（完整替换模式）。用于跟踪复杂任务的执行进度。\n\n"
                    "使用场景：\n"
                    "- 当你意识到需要多个步骤完成用户请求时（3步以上）\n"
                    "- 需要按顺序执行多个子任务时\n"
                    "- 需要跟踪长期任务的进度时\n\n"
                    "工作流程：\n"
                    "1. 创建任务清单：TodoWrite(items=[...])\n"
                    "2. 开始任务时：将status改为in_progress\n"
                    "3. 完成任务时：将status改为completed\n\n"
                    "约束规则：\n"
                    "- 最多20个任务\n"
                    "- 同时只能有一个in_progress状态的任务\n"
                    "- 必须包含content、status两个字段\n\n"
                    "示例：\n"
                    'TodoWrite(items=[\n'
                    '  {"content": "获取气象数据", "status": "completed"},\n'
                    '  {"content": "分析VOCs组分", "status": "in_progress"},\n'
                    '  {"content": "生成溯源报告", "status": "pending"}\n'
                    '])'
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {
                                        "type": "string",
                                        "description": "任务描述（简短明确），如'获取气象数据'"
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                        "description": (
                                            "任务状态：\n"
                                            "- pending: 待执行\n"
                                            "- in_progress: 执行中\n"
                                            "- completed: 已完成"
                                        )
                                    }
                                },
                                "required": ["content", "status"]
                            },
                            "description": "任务列表（完整替换，不是增量更新）"
                        }
                    },
                    "required": ["items"]
                }
            }
        }

        super().__init__(
            name="TodoWrite",
            description="更新任务清单（完整替换模式）",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True
        )
        # Mark that we need todo_list from context
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        items: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Execute TodoWrite tool

        Args:
            context: Execution context
            items: List of todo items

        Returns:
            Execution result with rendered todo list
        """
        try:
            # Import TodoList
            from app.agent.task.todo_models import TodoList

            # Get todo_list from context
            todo_list = context.get_task_list()

            # Check if this is the old TaskList or new TodoList
            if todo_list is None:
                # Create new TodoList
                todo_list = TodoList()
            elif not isinstance(todo_list, TodoList):
                # This is the old TaskList, create new TodoList instead
                logger.info("converting_old_tasklist_to_new_todolist")
                todo_list = TodoList()

            # Update todo list
            rendered = todo_list.update(items)

            logger.info(
                "todowrite_executed",
                session_id=context.session_id,
                item_count=len(items),
                rendered_summary=rendered.split('\n')[-1] if rendered else ""
            )

            return {
                "status": "success",
                "success": True,
                "data": {
                    "rendered": rendered,
                    "items": items
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite",
                    "field_mapping_applied": False
                },
                "summary": f"任务清单已更新 ({len(items)} 个任务)"
            }

        except ValueError as e:
            # Validation error (e.g., too many items, multiple in_progress)
            logger.error(f"TodoWrite validation failed: {e}")
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite"
                },
                "summary": f"任务清单更新失败: {str(e)}"
            }
        except Exception as e:
            logger.error(f"TodoWrite execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite"
                },
                "summary": f"任务清单更新失败: {str(e)}"
            }


# Create tool instance
todo_write_tool = TodoWriteTool()
