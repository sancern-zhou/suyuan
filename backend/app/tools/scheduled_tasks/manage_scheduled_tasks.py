"""Personal scheduled-task lifecycle using the same authorization as the Web API."""

from fastapi import HTTPException
from pydantic import ValidationError

from app.tools.base import LLMTool, ToolCategory
from .session_identity import resolve_task_user


class ManageScheduledTasksTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="manage_scheduled_tasks",
            description="管理当前用户的定时任务：列表、详情、修改、启停、删除、立即执行、执行历史及结果。",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "manage_scheduled_tasks",
                "description": (
                    "管理当前登录用户的定时任务，不接受用户ID。先 list 获取真实 task_id，再操作具体任务。"
                    "action: list/get/update/enable/disable/delete/execute/history/results。"
                    "execute 仅提交执行，不代表任务完成；用 history/results 查询后续结果。"
                    "update 的 updates 只传需要变更的任务配置，可用字段与创建任务一致；禁止修改归属及执行状态。"
                    "用户明确要求删除或执行即可操作，未明确要求时不要自行删除或试跑。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": [
                            "list", "get", "update", "enable", "disable", "delete", "execute", "history", "results"
                        ]},
                        "task_id": {"type": "string", "description": "list 以外必填，来自任务列表的任务ID"},
                        "updates": {
                            "type": "object", "description": "update 必填：仅传变更字段，未传字段保持原值",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "prompt": {"type": "string", "minLength": 1},
                                "execution_mode": {"type": "string", "enum": ["assistant", "expert", "ops", "query", "social", "custom", "workflow"]},
                                "schedule_type": {"type": "string", "enum": ["daily_8am", "every_2h", "every_30min", "monthly_1st_7am", "weekly_monday_8am", "once", "interval", "daily_custom", "weekly_custom", "monthly_custom", "quarterly_custom"]},
                                "run_at": {"type": "string", "description": "Asia/Shanghai 本地时间或带时区的 ISO 日期时间"},
                                "interval_minutes": {"type": "integer", "minimum": 1},
                                "hour": {"type": "integer", "minimum": 0, "maximum": 23},
                                "minute": {"type": "integer", "minimum": 0, "maximum": 59},
                                "day_of_week": {"type": "integer", "minimum": 0, "maximum": 6},
                                "day_of_month": {"type": "integer", "minimum": 1, "maximum": 31},
                                "enabled": {"type": "boolean"},
                                "timeout_seconds": {"type": "integer", "minimum": 1},
                                "model_tier": {"type": "string", "enum": ["auto", "flash", "pro"]},
                                "skill_id": {"type": ["string", "null"]},
                                "tool_names": {"type": "array", "items": {"type": "string"}},
                                "workflow_name": {"type": "string"},
                                "workflow_args": {"type": "object"},
                                "broadcast_enabled": {"type": "boolean"},
                                "target_user_ids": {"type": "array", "items": {"type": "string"}},
                                "tags": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "page": {"type": "integer", "minimum": 1, "default": 1},
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
        )

    async def execute(self, context=None, action=None, task_id=None, updates=None, page=1, page_size=20,
                      data_context_manager=None, **kwargs):
        try:
            from app.api import scheduled_task_routes as routes

            if action not in self.function_schema["parameters"]["properties"]["action"]["enum"]:
                raise ValueError("不支持的定时任务操作")
            if kwargs:
                raise ValueError("不支持额外参数")
            user = await resolve_task_user(context)
            service = routes.get_scheduled_task_service()
            page = max(1, int(page))
            page_size = min(50, max(1, int(page_size)))
            if action == "list":
                tasks = [task for task in service.list_tasks(enabled_only=False) if routes._can_access_task(task, user)]
                start = (page - 1) * page_size
                data = {"tasks": [t.model_dump(mode="json") for t in tasks[start:start + page_size]],
                        "total": len(tasks), "page": page, "page_size": page_size}
            else:
                if not task_id:
                    raise ValueError("请先查询任务列表，提供真实任务ID")
                task = service.get_task(task_id)
                if not task:
                    raise HTTPException(status_code=404, detail="任务不存在或无权访问")
                routes._require_task_access(task, user)
                if action == "get":
                    data = {"task": task.model_dump(mode="json")}
                elif action == "update":
                    if not isinstance(updates, dict) or not updates:
                        raise ValueError("请提供需要修改的任务配置")
                    unknown = set(updates) - set(routes.UpdateTaskRequest.model_fields)
                    if unknown:
                        raise ValueError(f"不允许修改字段：{', '.join(sorted(unknown))}")
                    result = await routes.update_task(task_id, routes.UpdateTaskRequest(**updates), user)
                    data = result.model_dump(mode="json")
                elif action in {"enable", "disable", "delete"}:
                    result = await getattr(routes, f"{action}_task")(task_id, user)
                    data = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
                elif action == "execute":
                    data = await routes.execute_task_now(task_id, user)
                elif action == "history":
                    result = await routes.get_task_executions(task_id, page=page, page_size=page_size, limit=None, user=user)
                    data = result.model_dump(mode="json")
                else:
                    records, total = service.list_task_results(task_id=task_id, page=page, page_size=page_size)
                    data = {"results": [r.model_dump(mode="json", exclude={"extra"}) for r in records],
                            "total": total, "page": page, "page_size": page_size}
            return {"success": True, "data": data, "summary": (
                "任务已提交执行，请查询执行历史及结果确认完成状态" if action == "execute" else "定时任务操作成功"
            )}
        except (HTTPException, ValueError, ValidationError) as exc:
            return {"success": False, "data": {}, "summary": str(getattr(exc, "detail", exc))}
        except Exception:
            return {"success": False, "data": {}, "summary": "定时任务服务或用户身份查询失败，未确认操作成功，请查询任务状态后重试"}


manage_scheduled_tasks_tool = ManageScheduledTasksTool()
