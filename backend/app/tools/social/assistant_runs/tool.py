"""Inspect and control real personal child/workflow executions."""

import structlog

from app.tools.base import LLMTool, ToolCategory


class ManageAssistantRunsTool(LLMTool):
    def __init__(self, service=None):
        self.service = service
        description = (
            "管理本人的办公或专业委派运行：list/get 查询真实运行，result 分页读取完整结果，"
            "cancel 请求停止，steer 向仍接受输入的单个办公子 Agent 补充文本要求。"
            "使用委派返回的 assistant_run_id/run_id，不是长期事项或调度计划 ID。"
            "补充要求或停止仅在 accepted=true 时受理；再次查询才能确认结束。"
            "unknown 表示执行器状态无法确认，不代表完成，不能自动重跑。"
        )
        super().__init__(
            name="manage_assistant_runs",
            description=description,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "manage_assistant_runs",
                "description": description,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "get", "result", "cancel", "steer"],
                        },
                        "run_id": {"type": "string"},
                        "message": {"type": "string", "maxLength": 20000},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20000},
                    },
                    "required": ["action"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        action=None,
        run_id=None,
        message=None,
        offset=0,
        limit=None,
        data_context_manager=None,
        **kwargs,
    ):
        try:
            from app.social.assistant_runs import AssistantRunService

            if kwargs or getattr(context, "runtime_mode", None) != "assistant":
                raise PermissionError("只允许当前助手会话管理本人的委派")
            limit = limit if limit is not None else (12000 if action == "result" else 20)
            if (
                type(offset) is not int
                or offset < 0
                or type(limit) is not int
                or not 1 <= limit <= 20000
            ):
                raise ValueError("分页参数无效")
            service = self.service or AssistantRunService()
            data = await service.command(
                context, action=action, run_id=run_id, message=message, offset=offset, limit=limit
            )
            return {"success": True, "status": "success", "data": data}
        except (ValueError, PermissionError) as exc:
            return {"success": False, "status": "failed", "error": str(exc)}
        except Exception:
            structlog.get_logger(__name__).exception("assistant_run_operation_failed")
            return {
                "success": False,
                "status": "failed",
                "error": "委派状态服务暂不可用，未自动重试执行",
            }
