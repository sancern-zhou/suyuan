"""监控通报提交工具（Watchdog → 运维助手收件箱）。

替代 broadcast_social_users 的直推通道：微信直推受官方互动窗口限制
已不可稳定送达（P0 最后一公里断裂），改为把通报落进
settings.monitor_report_owner 名下确定性助手会话——必达（落库）、
可回查（会话历史）、可跟进（运维在该会话里继续质询助手）。

边界设计：
- 门禁：仅运行监控定时任务（runtime-monitor 标签）上下文可调用，
  交互会话与其他任务不能借用系统通报通道；
- 未配置接收人（monitor_report_owner 为空）时拒绝投递并如实说明，
  禁止静默丢弃或转投其他通道；
- 只入队不阻塞：投递由回复时钟（start_result_replies，10s 周期）
  异步完成，工具调用不等待合成与落笔。
"""
from __future__ import annotations

from typing import Any, Dict

import structlog

from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)

MONITOR_TAG = "runtime-monitor"


def _refuse(summary: str) -> Dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "data": {},
        "metadata": {"tool_name": "submit_monitor_report"},
        "summary": summary,
    }


class SubmitMonitorReportTool(LLMTool):
    """Submit a watchdog report into the configured owner's assistant inbox."""

    def __init__(self):
        function_schema = {
            "name": "submit_monitor_report",
            "description": (
                "把运行监控通报提交到运维助手会话（唯一通报通道）。"
                "通报内容需已是面向用户的成稿：总体结论+逐条异常（对象、"
                "现象、根因、已执行动作、建议）。仅运行监控定时任务可调用；"
                "接收人由环境配置 monitor_report_owner 决定。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "通报正文（面向用户的完整成稿，不是摘要提示）",
                    },
                    "title": {
                        "type": "string",
                        "description": "可选。通报标题，默认「后台运行通报」",
                    },
                    "report_key": {
                        "type": "string",
                        "description": (
                            "可选。幂等键（如 execution_id 或事件 id）；"
                            "同一键重复提交不会产生重复通报"
                        ),
                    },
                },
                "required": ["content"],
            },
        }
        super().__init__(
            name="submit_monitor_report",
            description="把运行监控通报提交到运维助手会话",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        content: str = "",
        title: str = "",
        report_key: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        scheduled_context = getattr(context, "scheduled_task_context", None)
        if not isinstance(scheduled_context, dict) or not scheduled_context.get("task_id"):
            return _refuse("当前不是定时任务执行上下文，不能提交通报")
        if not (content or "").strip():
            return _refuse("缺少通报正文 content 参数")

        task_id = str(scheduled_context.get("task_id"))
        try:
            from app.scheduled_tasks.service import get_scheduled_task_service

            service = get_scheduled_task_service()
        except Exception:
            service = None
        if service is None:
            return _refuse("定时任务服务不可用，无法校验通报来源")
        task = service.task_storage.get(task_id)
        if task is None:
            return _refuse(f"任务不存在：{task_id}")
        if MONITOR_TAG not in (task.tags or []):
            return _refuse("仅运行监控任务（runtime-monitor）可使用系统通报通道")

        from config.settings import settings

        if not (settings.monitor_report_owner or "").strip():
            return _refuse(
                "通报接收人未配置（monitor_report_owner 为空），本次通报未送达；"
                "请在后端环境文件配置该用户后重试，不要改用其他通道"
            )

        try:
            from app.social.assistant_notifications import AssistantNotificationService

            message_id = await AssistantNotificationService().enqueue_monitor_report(
                project=settings.project_id,
                content=content,
                title=(title or "").strip() or None,
                report_key=(report_key or "").strip() or None,
            )
        except Exception as exc:  # noqa: BLE001 - 投递链故障必须如实上报
            logger.warning("monitor_report_submit_failed", task_id=task_id, error=str(exc))
            return _refuse(f"通报入队失败：{exc}")

        if message_id is None:
            return _refuse(
                "通报接收人配置无效（monitor_report_owner 为空或 system），本次通报未送达"
            )
        return {
            "status": "success",
            "success": True,
            "data": {"message_id": message_id},
            "metadata": {"tool_name": "submit_monitor_report", "task_id": task_id},
            "summary": "通报已入队，将由回复时钟投递到运维助手会话",
        }


submit_monitor_report_tool = SubmitMonitorReportTool()
