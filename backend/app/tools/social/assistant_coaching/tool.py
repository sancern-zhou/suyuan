"""Project-grounded coaching in the current social turn; no extra model runtime."""

import structlog

from app.social.assistant_coaching import AssistantCoachingService
from app.social.assistant_request import require_assistant_request
from app.tools.base import LLMTool, ToolCategory
from app.tools.scheduled_tasks.session_identity import resolve_task_user


class ManageAssistantCoachingTool(LLMTool):
    def __init__(self, service=None):
        self.service = service or AssistantCoachingService()
        super().__init__(
            name="manage_assistant_coaching",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            description="查询当前项目实际能力，保存具体使用建议，记录采纳或忽略，生成下一步操作。",
            function_schema={
                "name": "manage_assistant_coaching",
                "description": (
                    "discover 从当前项目配置和已启用工具发现能力，可按 kind 或 capability_id 查询，支持分页。"
                    "先查询再推荐；propose 只在当前用户有需要时提供1至2条具体建议，"
                    "写明目标、推荐理由、可直接使用的提问文本及缺少的信息，不猜数据或参数。"
                    "list 查询已有建议，dismiss 后相同能力和目标不再推荐。"
                    "accept/dismiss 必须来自当前用户明确选择，并带 suggestion_id 和 expected_version。"
                    "accept 仅保存选择并返回 next_action，不执行任务、不建事项、不切换模式、不授予后台或消息权限。"
                    "当前可直接使用的工具优先，只有确有必要才委派；workspace 表示专业主入口，不可当子Agent调用。"
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["discover", "propose", "list", "accept", "dismiss"],
                        },
                        "capability_id": {"type": "string"},
                        "kind": {"type": "string", "enum": ["tool", "workspace", "delegate"]},
                        "goal": {"type": "string", "maxLength": 2000},
                        "reason": {"type": "string", "maxLength": 2000},
                        "suggested_prompt": {"type": "string", "maxLength": 6000},
                        "missing_inputs": {
                            "type": "array",
                            "maxItems": 10,
                            "items": {"type": "string", "maxLength": 500},
                        },
                        "suggestion_id": {"type": "string"},
                        "expected_version": {"type": "integer", "minimum": 1},
                        "state": {
                            "type": "string",
                            "enum": ["pending", "accepted", "dismissed", "all"],
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        "offset": {"type": "integer", "minimum": 0},
                    },
                    "required": ["action"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        action=None,
        capability_id=None,
        kind=None,
        goal=None,
        reason=None,
        suggested_prompt=None,
        missing_inputs=None,
        suggestion_id=None,
        expected_version=None,
        state="pending",
        limit=20,
        offset=0,
        data_context_manager=None,
        **kwargs,
    ):
        try:
            if kwargs:
                raise ValueError("不支持额外参数或用户身份参数")
            from config.settings import settings

            user = await resolve_task_user(context)
            project = settings.project_id
            if action == "discover":
                catalog = self.service.catalog()
                items = list(catalog.values())
                if kind is not None:
                    if kind not in {"tool", "workspace", "delegate"}:
                        raise ValueError("不支持的能力类型")
                    items = [item for item in items if item["kind"] == kind]
                if capability_id is not None:
                    items = [item for item in items if item["capability_id"] == capability_id]
                start, size = max(0, int(offset)), max(1, min(50, int(limit)))
                data = {
                    "project": project,
                    "capabilities": items[start : start + size],
                    "total": len(items),
                }
            elif action == "list":
                data = {
                    "suggestions": await self.service.list(
                        project, user.id, state=state, limit=limit, offset=offset
                    )
                }
            elif action in {"propose", "accept", "dismiss"}:
                request = require_assistant_request(context.session_id)
                if getattr(context, "scheduled_task_context", None):
                    raise PermissionError("后台计划不能代替用户选择建议")
                if action == "propose":
                    data = await self.service.propose(
                        project,
                        user.id,
                        request,
                        capability_id=capability_id,
                        goal=goal,
                        reason=reason,
                        suggested_prompt=suggested_prompt,
                        missing_inputs=missing_inputs,
                    )
                else:
                    data = await self.service.decide(
                        project,
                        user.id,
                        request,
                        suggestion_id=suggestion_id,
                        expected_version=expected_version,
                        action=action,
                    )
            else:
                raise ValueError("不支持的教练操作")
            return {
                "success": True,
                "status": "success",
                "data": data,
                "summary": "建议选择已保存，任务尚未启动" if action == "accept" else "教练操作成功",
            }
        except (ValueError, PermissionError) as exc:
            return {"success": False, "status": "failed", "error": str(exc)}
        except Exception:
            structlog.get_logger(__name__).exception("assistant_coaching_failed")
            return {
                "success": False,
                "status": "failed",
                "error": "能力或建议服务暂不可用，请稍后重试",
            }
