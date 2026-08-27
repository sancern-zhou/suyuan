"""Run pending Xuchang Scenario 2 NOAA trajectory jobs."""

from __future__ import annotations

from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_transport_escalation import (
    COMPLETED_EVENT_TYPE,
    XuchangTransportEscalationService,
)
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()


class XuchangTransportAnalysisFetcher(DataFetcher):
    def __init__(self, service: XuchangTransportEscalationService | None = None) -> None:
        super().__init__(
            name="xuchang_transport_analysis_fetcher",
            description="许昌场景二NOAA后向轨迹与本地输送诊断",
            schedule="25 * * * *",
            version="2.0.0",
        )
        self.service = service or XuchangTransportEscalationService()

    async def fetch_and_store(self) -> dict[str, Any]:
        results = await self.service.run_pending(limit=1)
        if results:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
            for result in results:
                if result.get("event_type") != COMPLETED_EVENT_TYPE:
                    continue
                await task_service.publish_event(TaskEvent(
                    event_id=result["event_id"],
                    event_type=COMPLETED_EVENT_TYPE,
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
                        "target_pollutant": result["target_pollutant"],
                        "status": result["status"],
                        "diagnosis": result["transport_diagnosis"]["classification"],
                        "evidence_package_path": result["evidence_package_path"],
                    },
                ))
        logger.info("xuchang_transport_analysis_completed", job_count=len(results))
        return {"jobs": results, "job_count": len(results)}
