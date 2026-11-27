"""④污染原因分析通报的微信群补投钩子（Agent 模式执行后投微信群）。

任务由固定工作流改为报告模式 Agent 驱动后，通报文案与报告包由 Agent 经
broadcast_social_users 投递 APP；微信群文件队列没有 Agent 工具入口，由本
事件结果钩子在执行成功后补投：取广播工具调用的文案与 DOCX 附件入队（与
工作流时代同一队列、同一 kind 与附件格式）。钩子失败只记日志，不影响任
务执行状态。

注册时机：worker/web 启动的 xuchang 项目工作流注册块（lifecycle.scheduled）
一并调用 register_pollution_cause_wechat_sink()，幂等登记。
"""

from __future__ import annotations

from typing import Any

import structlog

from app.scheduled_tasks.event_result_hooks import register_event_result_handler
from app.scenarios.xuchang_station_deviation.wechat_push_queue import (
    enqueue_wechat_message,
)

logger = structlog.get_logger()

TASK_ID = "task_xuchang_pollution_cause_analysis"
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def extract_broadcast_payload(execution: Any) -> tuple[str, list[str]]:
    """从执行记录里取最后一次成功的 broadcast_social_users 调用载荷。

    返回 (广播文案, media 路径列表)；无成功广播调用返回 ("", [])。
    """
    steps = list(getattr(execution, "steps", None) or [])
    for step in reversed(steps):
        calls = list(getattr(step, "tool_calls", None) or [])
        for call in reversed(calls):
            if not isinstance(call, dict) or call.get("tool") != "broadcast_social_users":
                continue
            if call.get("success") is False:
                continue
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            message = str(args.get("message") or "").strip()
            if not message:
                continue
            media: list[str] = []
            for value in (args.get("media") or []) + list(call.get("media") or []):
                path = str(value or "").strip()
                if path and path not in media:
                    media.append(path)
            return message, media
    return "", []


def _first_docx(paths: list[str]) -> str | None:
    for path in paths:
        if str(path).lower().endswith(".docx"):
            return path
    return None


def register_pollution_cause_wechat_sink() -> None:
    """登记事件结果钩子（每进程一次）。"""

    register_event_result_handler(sink_dispatch)


async def sink_dispatch(task: Any, event: Any, execution: Any) -> None:
    """事件结果钩子本体：任务成功后按广播载荷补投微信群队列。"""
    from app.scheduled_tasks.models.execution import ExecutionStatus

    if getattr(task, "task_id", None) != TASK_ID:
        return
    if getattr(execution, "status", None) != ExecutionStatus.SUCCESS:
        return
    message, media = extract_broadcast_payload(execution)
    if not message:
        logger.warning(
            "xuchang_pollution_cause_wechat_sink_skipped",
            execution_id=getattr(execution, "execution_id", None),
            reason="no_successful_broadcast_call",
        )
        return
    docx_path = _first_docx(media)
    target_date = str((getattr(event, "payload", None) or {}).get("target_date") or "")
    attachments = []
    if docx_path:
        # 广播 media 来自 create_report_package 成品资源，可能是项目相对路径
        # 或绝对路径；统一归一化为项目相对路径（web 侧 /attachment 端点按同
        # 一契约解析），与工作流时代的队列格式保持一致。
        from app.utils.path_config import format_agent_path

        normalized = docx_path
        if str(docx_path).startswith("/"):
            normalized = format_agent_path(docx_path)
        attachments.append({
            "path": normalized,
            "filename": f"污染原因分析通报_{target_date.replace('-', '') or 'unknown'}.docx",
            "mime": DOCX_MIME_TYPE,
        })
    enqueued = enqueue_wechat_message(
        "pollution_cause",
        message,
        media=[],
        attachments=attachments,
        metadata={
            "scenario": "pollution_cause_analysis",
            "target_date": target_date,
            "execution_id": str(getattr(execution, "execution_id", "") or ""),
        },
    )
    logger.info(
        "xuchang_pollution_cause_wechat_sink_enqueued" if enqueued
        else "xuchang_pollution_cause_wechat_sink_skipped",
        execution_id=getattr(execution, "execution_id", None),
        message_id=(enqueued or {}).get("id"),
        has_attachment=bool(attachments),
    )
