"""Human-authorized owner-only reminder controls."""

import structlog

from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_request import require_assistant_request
from app.tools.base import LLMTool, ToolCategory
from app.tools.scheduled_tasks.session_identity import resolve_task_user


class ManageAssistantFollowupsTool(LLMTool):
    def __init__(self, service=None):
        self.service = service or AssistantFollowupService()
        super().__init__(
            name="manage_assistant_followups",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            description="为当前用户的事项设置个人提醒、查询运行及投递记录、停止提醒。",
            function_schema={
                "name": "manage_assistant_followups",
                "description": "仅用户明确要求提醒时 create。先查询事项 task_id/version；不会自动分析或标记完成。"
                "只提醒当前入口的本人，不接受收件人参数。list 查询实际计划、执行及投递状态。"
                "disable 停止该事项所有提醒。unknown 表示投递结果不确定，不能声称已送达或自动重发。",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "list", "disable"]},
                        "task_id": {"type": "string"},
                        "expected_version": {"type": "integer", "minimum": 1},
                        "kind": {"type": "string", "enum": ["now", "once", "interval", "cron"]},
                        "instructions": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "run_at": {
                            "type": "string",
                            "description": "ISO8601 时间，建议含时区；无时区按 timezone_name",
                        },
                        "interval_minutes": {"type": "integer", "minimum": 1, "maximum": 525600},
                        "cron": {
                            "type": "string",
                            "description": "五段 cron，分钟 小时 日 月 星期",
                        },
                        "timezone_name": {"type": "string", "default": "Asia/Shanghai"},
                    },
                    "required": ["action", "task_id"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        action=None,
        task_id=None,
        expected_version=None,
        kind=None,
        instructions=None,
        run_at=None,
        interval_minutes=None,
        cron=None,
        timezone_name="Asia/Shanghai",
        data_context_manager=None,
        **kwargs,
    ):
        try:
            from config.settings import settings

            if not settings.assistant_followups_enabled:
                raise PermissionError("个人事项提醒尚未启用，未创建计划")
            if kwargs:
                raise ValueError("不支持额外参数或收件人参数")
            user = await resolve_task_user(context)
            if action == "list":
                data = await self.service.inspect(settings.project_id, user.id, task_id)
            else:
                request = require_assistant_request(context.session_id)
                if getattr(context, "scheduled_task_context", None):
                    raise PermissionError("后台计划不能替用户设置提醒")
                if action == "create":
                    data = await self.service.create(
                        settings.project_id,
                        user.id,
                        task_id,
                        request,
                        expected_version=expected_version,
                        kind=kind,
                        instructions=instructions,
                        run_at=run_at,
                        interval_minutes=interval_minutes,
                        cron=cron,
                        timezone_name=timezone_name,
                    )
                elif action == "disable":
                    data = await self.service.disable(
                        settings.project_id,
                        user.id,
                        task_id,
                        request,
                        expected_version=expected_version,
                    )
                else:
                    raise ValueError("不支持的提醒操作")
            return {
                "success": True,
                "status": "success",
                "data": data,
                "summary": "提醒操作已保存；投递情况以 notifications 为准",
            }
        except (ValueError, PermissionError) as exc:
            return {"success": False, "status": "failed", "error": str(exc)}
        except Exception:
            structlog.get_logger(__name__).exception("assistant_followup_operation_failed")
            return {
                "success": False,
                "status": "failed",
                "error": "提醒服务暂不可用，请稍后查询核实；没有切换到临时存储",
            }
