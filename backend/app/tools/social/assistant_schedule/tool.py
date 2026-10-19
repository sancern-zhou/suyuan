"""One scheduling tool; writes always go to the single worker over authenticated HTTP."""

import httpx
from pydantic import ValidationError

from app.auth.internal_identity import INTERNAL_USER_HEADER, encode_internal_user
from app.social.assistant_plans import PlanCommand
from app.social.assistant_request import require_assistant_request
from app.tools.base import LLMTool, ToolCategory
from app.tools.scheduled_tasks.session_identity import resolve_task_user


class ManageAssistantScheduleTool(LLMTool):
    def __init__(self, client_factory=httpx.AsyncClient):
        self.client_factory = client_factory
        description = (
            "统一管理当前用户的提醒、事项跟进和后台办公/专业执行计划。"
            "action=create/list/get/update/pause/resume/cancel/history/results。"
            "先 list/get 获取真实 plan_id 和 revision；修改传 expected_revision。"
            "create: purpose=remind 只提醒本人，自动登记提醒事项；followup 绑定已有事项并执行已授权只读分析，"
            "需 task_id/expected_version；execute 指定当前项目办公或专业 execution_mode。"
            "schedule 指定 once/interval/cron/feedback 与时区；feedback 只在该事项收到新反馈时触发跟进，"
            "不会读取微信群。普通提醒不能升级为分析或任意发信。"
            "只在用户明确交办时创建或修改，不接受收件人。"
            "pause 暂停后可 resume；cancel 永久停止后续触发，不能恢复。"
            "停止后查询真实执行和投递记录，已运行的专业任务可能继续，已发出消息无法撤回。"
            "创建成功只表示登记计划，不等于已执行或已送达。"
            "后台功能关闭时不能绕过开关；仍可查询和停止。"
        )
        super().__init__(
            name="manage_assistant_schedule",
            description=description,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "manage_assistant_schedule",
                "description": description,
                "parameters": PlanCommand.model_json_schema(),
            },
        )

    async def execute(self, context=None, data_context_manager=None, **kwargs):
        try:
            from config.settings import settings

            command = PlanCommand.model_validate(kwargs)
            user = await resolve_task_user(context)
            payload = {
                "command": command.model_dump(mode="json", exclude_none=True),
                "source_session_id": context.session_id,
            }
            if command.action not in {"list", "get", "history", "results"}:
                if getattr(context, "scheduled_task_context", None):
                    raise PermissionError("后台任务不能替用户新增或修改计划")
                grant = require_assistant_request(context.session_id)
                payload.update(
                    request_id=grant.request_id,
                    user_message=grant.user_message,
                    delivery_user_id=grant.delivery_user_id,
                )
            secret = settings.social_worker_internal_token
            headers = {INTERNAL_USER_HEADER: encode_internal_user(user, secret=secret)}
            if secret:
                headers["x-social-worker-token"] = secret
            base_url = settings.social_worker_internal_url.rstrip("/") or (
                f"http://127.0.0.1:{settings.social_worker_internal_port}"
            )
            async with self.client_factory(timeout=30) as client:
                response = await client.post(
                    base_url + "/internal/assistant-schedule",
                    json=payload,
                    headers=headers,
                )
            if response.is_error:
                return {
                    "success": False,
                    "status": "failed",
                    "error": response.json().get("detail"),
                    "http_status": response.status_code,
                }
            return {
                "success": True,
                "status": "success",
                "data": response.json(),
                "summary": "计划操作已保存；运行和消息状态请查询 history/results",
            }
        except (ValueError, PermissionError, ValidationError) as exc:
            return {"success": False, "status": "failed", "error": str(exc)}
        except Exception:
            import structlog

            structlog.get_logger(__name__).exception("assistant_schedule_worker_request_failed")
            return {
                "success": False,
                "status": "unknown",
                "error": "调度服务未确认结果，请先查询计划，避免重复创建；没有使用本地临时调度",
            }
