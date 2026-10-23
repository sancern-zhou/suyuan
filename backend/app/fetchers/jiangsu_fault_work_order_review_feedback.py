"""Consume queued fault work order review decision feedback confirmations."""

from __future__ import annotations

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.jiangsu_fault_work_order_review_feedback import (
    POLL_SCHEDULE,
    consume_pending_feedback,
)
from app.tools.jiangsu.demo_freeze import demo_freeze_active, demo_freeze_skip_result

logger = structlog.get_logger(__name__)


class JiangsuFaultWorkOrderReviewFeedbackFetcher(DataFetcher):
    """每分钟领取人工审核决策触发的反馈确认队列。

    队列为空时仅做一次目录读取，不产生任何外部调用；有待处理条目（人工结论
    与 AI 原结论不一致的审核决策）时做一次小 LLM 一致性确认，并把确认结果
    以 assistant 消息追加进原审核会话，「进入对话区」即可看到。案例库与长期
    记忆由任务人工反馈学习管道独立沉淀。
    """

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fault_work_order_review_feedback",
            description="领取故障工单审核人工决策队列，生成结论一致性确认写入原审核会话",
            schedule=POLL_SCHEDULE,
            version="1.0.0",
        )

    async def fetch_and_store(self) -> dict[str, int]:
        if demo_freeze_active():
            return demo_freeze_skip_result(self.name)
        stats = await consume_pending_feedback()
        if stats.get("done") or stats.get("failed"):
            logger.info("work_order_review_feedback_cycle", **stats)
        return stats
