"""Run pending Xuchang Scenario 3 NOAA trajectory jobs."""

from __future__ import annotations

from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_transport_escalation import (
    COMPLETED_EVENT_TYPE,
    XuchangTransportEscalationService,
)
from app.scenarios.xuchang_transport_escalation.service import PROCESS_COMPLETED_EVENT_TYPE
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()


class XuchangTransportAnalysisFetcher(DataFetcher):
    def __init__(self, service: XuchangTransportEscalationService | None = None) -> None:
        super().__init__(
            name="xuchang_transport_analysis_fetcher",
            description="许昌场景三NOAA后向轨迹与本地输送诊断",
            # 单轮约 3~4 分钟，须避开河南 ssfb 三抓取器窗口（城市 14,20,55 / 站点 16,22,57 /
            # 区县 18,24,59）：此前 */15 的 :15 轮拖到 :18:26，与县级抓取并发连
            # Crawler MySQL 触发 "Packet sequence number wrong"（Crawler MySQL 并发
            # 握手易乱包，严禁与 ssfb 三兄弟同窗口运行）。
            schedule="26,31,40,50 * * * *",
            version="3.1.1",
        )
        self.service = service or XuchangTransportEscalationService()

    async def fetch_and_store(self) -> dict[str, Any]:
        results = await self.service.run_pending(limit=2)
        if results:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
            for result in results:
                event_type = result.get("event_type")
                if event_type not in {COMPLETED_EVENT_TYPE, PROCESS_COMPLETED_EVENT_TYPE}:
                    continue
                await task_service.publish_event(TaskEvent(
                    event_id=result["event_id"],
                    event_type=event_type,
                    occurred_at=result["generated_at"],
                    attributes={
                        "city": result["city"],
                        "target_pollutant": result["target_pollutant"],
                        "station_id": result["station_id"],
                        "diagnosis": result["transport_diagnosis"]["classification"],
                    },
                    payload={
                        "analysis_id": result["analysis_id"],
                        "city": result["city"],
                        "station_id": result["station_id"],
                        "station_name": result["station_name"],
                        "target_date": result["target_date"],
                        "process_window": result.get("process_window"),
                        "target_pollutant": result["target_pollutant"],
                        "status": result["status"],
                        "diagnosis": result["transport_diagnosis"]["classification"],
                        "evidence_package_path": result["evidence_package_path"],
                    },
                ))
        logger.info("xuchang_transport_analysis_completed", job_count=len(results))
        return {"jobs": results, "job_count": len(results)}
