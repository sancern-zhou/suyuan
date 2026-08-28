"""Fast station-deviation trigger for the Xuchang Scenario 1 workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_station_deviation.episodes import (
    XuchangStationDeviationEpisodeService,
)
from app.scenarios.xuchang_station_deviation.evidence import (
    XuchangStationDeviationEvidenceCollector,
)
from app.scenarios.xuchang_station_deviation.service import (
    EVENT_TYPE,
    XuchangStationDeviationAlertService,
)
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path


logger = structlog.get_logger()
EPISODE_CLOSED_EVENT_TYPE = "xuchang.station_deviation.episode_closed"


class XuchangStationDeviationAlertFetcher(DataFetcher):
    def __init__(
        self,
        service: XuchangStationDeviationAlertService | None = None,
        analysis_tool: Any | None = None,
        episode_service: XuchangStationDeviationEpisodeService | None = None,
        evidence_collector: XuchangStationDeviationEvidenceCollector | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_station_deviation_alert_fetcher",
            description="许昌场景一站点空间偏差阈值告警",
            # Poll every minute so a slow 5-minute ingestion run is analyzed
            # on the next tick instead of waiting for another five-minute slot.
            schedule="* * * * *",
            version="1.1.0",
        )
        self.service = service or XuchangStationDeviationAlertService()
        # Kept as a compatibility argument for callers; source attribution is
        # intentionally no longer run in the event-driven alert path.
        self.episode_service = episode_service or XuchangStationDeviationEpisodeService()
        self.evidence_collector = evidence_collector or XuchangStationDeviationEvidenceCollector()

    async def fetch_and_store(self) -> dict[str, Any]:
        result = await self.service.run()
        target_hour = datetime.fromisoformat(result["target_hour"])
        closed_episodes = self.episode_service.close_stale(target_hour)
        if result["alerts"] or closed_episodes:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
            for episode in closed_episodes:
                await task_service.publish_event(TaskEvent(
                    event_id=f"{episode['episode_id']}-closed",
                    event_type=EPISODE_CLOSED_EVENT_TYPE,
                    occurred_at=episode["closed_at"],
                    attributes={
                        "city": episode["city"],
                        "target_pollutant": episode["target_pollutant"],
                        "station_id": episode["station_id"],
                    },
                    payload=episode,
                ))
            for alert in result["alerts"]:
                episode_result = self.episode_service.record(alert)
                alert["scenario_1_episode"] = {
                    "episode_id": episode_result["episode"]["episode_id"],
                    "status": episode_result["status"],
                    "reason": episode_result.get("reason"),
                    "should_analyze": episode_result["should_analyze"],
                }
                if not episode_result["should_analyze"]:
                    continue
                try:
                    evidence = await self.evidence_collector.collect(
                        alert=alert,
                        source_screening={
                            "status": "not_run",
                            "reason": "event alert path reports monitoring facts; upwind enterprise analysis is disabled",
                        },
                    )
                    evidence_path = self.service.write_evidence_package(alert, evidence)
                    alert["evidence_package_path"] = format_agent_path(evidence_path)
                    alert["evidence_collection"] = evidence["collection"]
                except Exception as exc:
                    logger.exception(
                        "xuchang_scenario_1_evidence_collection_failed",
                        event_id=alert["event_id"],
                    )
                    alert["evidence_collection"] = {
                        "status": "failed",
                        "errors": [{"asset": "evidence_package", "error": str(exc)}],
                    }
                await task_service.publish_event(TaskEvent(
                    event_id=alert["event_id"],
                    event_type=EVENT_TYPE,
                    occurred_at=alert["occurred_at"],
                    attributes={
                        "city": alert["city"],
                        "target_pollutant": alert["target_pollutant"],
                        "station_id": alert["station_id"],
                    },
                    payload=alert,
                ))
        result["closed_episodes"] = closed_episodes
        logger.info("xuchang_station_deviation_alert_completed", alert_count=len(result["alerts"]), target_hour=result["target_hour"])
        return result
