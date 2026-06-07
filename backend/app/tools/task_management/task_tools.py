"""Claude-style incremental task management tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agent.context.execution_context import ExecutionContext
from app.agent.task.task_models import TaskList, TaskStatus
from app.tools.base import LLMTool, ToolCategory


def _task_list(context: ExecutionContext) -> TaskList:
    task_list = context.get_task_list()
    if isinstance(task_list, TaskList):
        return task_list
    task_list = TaskList()
    context.task_list = task_list
    return task_list


class TaskCreateTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="TaskCreate",
            description="创建一个新任务。用于复杂多步骤任务的增量任务管理。",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "TaskCreate",
                "description": "Create a task in the current session task list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "简短、可执行的任务标题"},
                        "description": {"type": "string", "description": "任务需要完成的具体内容"},
                        "activeForm": {
                            "type": "string",
                            "description": "任务执行中显示的现在进行时描述，可选",
                        },
                    },
                    "required": ["subject", "description"],
                },
            },
        )
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        subject: str,
        description: str,
        activeForm: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_list = _task_list(context)
        existing = task_list.find_by_content(subject, description)
        if existing is not None:
            return {
                "status": "no_op",
                "success": True,
                "no_op": True,
                "data": {
                    "task": existing.to_dict(),
                    "existingTaskId": existing.id,
                },
                "summary": f"Task #{existing.id} already exists: {existing.subject}",
            }

        task = task_list.create(subject, description, activeForm)
        return {
            "status": "success",
            "success": True,
            "data": {"task": {"id": task.id, "subject": task.subject}},
            "summary": f"Task #{task.id} created successfully: {task.subject}",
        }


class TaskUpdateTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="TaskUpdate",
            description="更新单个任务的字段或状态。不要重复提交无变化更新。",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "TaskUpdate",
                "description": "Update one task in the current session task list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "taskId": {"type": "string", "description": "任务 ID"},
                        "subject": {"type": "string", "description": "新的任务标题，可选"},
                        "description": {"type": "string", "description": "新的任务描述，可选"},
                        "activeForm": {"type": "string", "description": "新的执行中描述，可选"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "deleted"],
                            "description": "新的任务状态；deleted 表示删除任务",
                        },
                    },
                    "required": ["taskId"],
                },
            },
        )
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        taskId: str,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        activeForm: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_list = _task_list(context)
        existing = task_list.get(taskId)
        if existing is None:
            return {
                "status": "failed",
                "success": False,
                "data": {"taskId": taskId, "updatedFields": []},
                "summary": f"Task #{taskId} not found",
            }

        if status == "deleted":
            deleted = task_list.delete(taskId)
            return {
                "status": "success" if deleted else "failed",
                "success": deleted,
                "data": {
                    "taskId": taskId,
                    "updatedFields": ["deleted"] if deleted else [],
                    "statusChange": {"from": existing.status.value, "to": "deleted"} if deleted else None,
                },
                "summary": f"Deleted task #{taskId}" if deleted else f"Task #{taskId} not found",
            }

        updates: Dict[str, Any] = {}
        updated_fields = []
        if subject is not None and subject != existing.subject:
            updates["subject"] = subject
            updated_fields.append("subject")
        if description is not None and description != existing.description:
            updates["description"] = description
            updated_fields.append("description")
        if activeForm is not None and activeForm != existing.active_form:
            updates["active_form"] = activeForm
            updated_fields.append("activeForm")

        next_status = TaskStatus(status) if status is not None else existing.status
        status_change = None
        if next_status != existing.status:
            updates["status"] = next_status
            updated_fields.append("status")
            status_change = {"from": existing.status.value, "to": next_status.value}

        if not updates:
            return {
                "status": "no_op",
                "success": True,
                "no_op": True,
                "data": {"taskId": taskId, "updatedFields": []},
                "summary": f"Task #{taskId} unchanged. Continue the current business task.",
            }

        task = task_list.update(taskId, **updates)
        return {
            "status": "success",
            "success": True,
            "data": {
                "taskId": task.id,
                "updatedFields": updated_fields,
                "statusChange": status_change,
                "task": task.to_dict(),
            },
            "summary": f"Updated task #{task.id} {', '.join(updated_fields)}",
        }


class TaskListTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="TaskList",
            description="列出当前会话任务清单。创建新任务前可用它检查重复任务。",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "TaskList",
                "description": "List tasks in the current session task list.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        )
        self.requires_task_list = True

    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        tasks = [task.to_dict() for task in _task_list(context).list()]
        return {
            "status": "success",
            "success": True,
            "data": {"tasks": tasks},
            "summary": f"{len(tasks)} active tasks",
        }


class TaskGetTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="TaskGet",
            description="按任务 ID 获取当前会话中的单个任务。",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "TaskGet",
                "description": "Get a task by ID from the current session task list.",
                "parameters": {
                    "type": "object",
                    "properties": {"taskId": {"type": "string", "description": "任务 ID"}},
                    "required": ["taskId"],
                },
            },
        )
        self.requires_task_list = True

    async def execute(self, context: ExecutionContext, taskId: str) -> Dict[str, Any]:
        task = _task_list(context).get(taskId)
        if task is None:
            return {
                "status": "failed",
                "success": False,
                "data": {"task": None},
                "summary": f"Task #{taskId} not found",
            }
        return {
            "status": "success",
            "success": True,
            "data": {"task": task.to_dict()},
            "summary": f"Task #{task.id}: {task.subject}",
        }


task_create_tool = TaskCreateTool()
task_update_tool = TaskUpdateTool()
task_list_tool = TaskListTool()
task_get_tool = TaskGetTool()
