"""Dispatch queued fault work order review reject reruns."""

from __future__ import annotations

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.jiangsu_fault_work_order_review_rerun import (
    POLL_SCHEDULE,
    publish_pending_reruns,
)
from app.tools.jiangsu.demo_freeze import demo_freeze_active, demo_freeze_skip_result

logger = structlog.get_logger(__name__)


class JiangsuFaultWorkOrderReviewRerunFetcher(DataFetcher):
    """每分钟领取人工退回触发的增量复审队列并派发审核事件。

    队列为空时仅做一次目录读取，不产生任何外部调用；有待处理条目时在
    worker 进程内重建原审核事件（注入人工退回意见与上一轮结论）并重开
    事件执行声明，由故障工单审核 Agent 完成增量复审。
    """

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fault_work_order_review_rerun",
            description="领取故障工单审核人工退回队列，派发带退回意见的增量复审事件",
            schedule=POLL_SCHEDULE,
            version="1.0.0",
        )

    async def fetch_and_store(self) -> dict[str, int]:
        if demo_freeze_active():
            return demo_freeze_skip_result(self.name)
        stats = await publish_pending_reruns()
        if stats.get("dispatched") or stats.get("failed"):
            logger.info("fault_work_order_review_rerun_cycle", **stats)
        return stats
