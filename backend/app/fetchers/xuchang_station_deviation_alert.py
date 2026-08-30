"""Fast station-deviation trigger for the Xuchang Scenario 1 workflow."""

from __future__ import annotations

import asyncio
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
            # 中大分钟抓取在每个 5 分钟槽的第 1 分钟启动；本任务在入口
            # 延迟 30 秒，给抓取和入库留出时间（01:30、06:30...）。
            schedule="1-59/5 * * * *",
            version="1.2.0",
        )
        self.service = service or XuchangStationDeviationAlertService()
        # Kept as a compatibility argument for callers; source attribution is
        # intentionally no longer run in the event-driven alert path.
        self.episode_service = episode_service or XuchangStationDeviationEpisodeService()
        self.evidence_collector = evidence_collector or XuchangStationDeviationEvidenceCollector()

    async def fetch_and_store(self) -> dict[str, Any]:
        await asyncio.sleep(30)
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
            analyzable_by_station: dict[str, list[dict[str, Any]]] = {}
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
                analyzable_by_station.setdefault(str(alert["station_id"]), []).append(alert)

            # 一个站点 episode 内的多个污染物共用一次 Agent 分析，避免同一
            # 站点在同一批次产生多条几乎相同的处置消息。
            for station_id, alerts in analyzable_by_station.items():
                evidences = []
                for alert in alerts:
                    try:
                        evidence = await self.evidence_collector.collect(
                            alert=alert,
                            source_screening={
                                "status": "not_run",
                                "reason": "event alert path reports monitoring facts; upwind enterprise analysis is disabled",
                            },
                        )
                        evidences.append({"alert": alert, "evidence": evidence})
                    except Exception as exc:
                        logger.exception("xuchang_scenario_1_evidence_collection_failed", event_id=alert["event_id"])
                        alert["evidence_collection"] = {"status": "failed", "errors": [{"asset": "evidence_package", "error": str(exc)}]}
                if not evidences:
                    continue
                primary = alerts[0]
                episode_path = self.service.write_episode_evidence_package(
                    station_id=station_id,
                    occurred_at=primary["occurred_at"],
                    alerts=evidences,
                )
                payload = {
                    **primary,
                    "station_episode_alerts": alerts,
                    "evidence_package_path": format_agent_path(episode_path),
                    "station_episode": True,
                }
                event_id = f"xuchang-station-episode-{primary['occurred_at'].replace(':', '').replace('+', '')}-{station_id}"
                await task_service.publish_event(TaskEvent(
                    event_id=event_id,
                    event_type=EVENT_TYPE,
                    occurred_at=primary["occurred_at"],
                    attributes={"city": primary["city"], "target_pollutant": primary["target_pollutant"], "station_id": station_id},
                    payload=payload,
                ))
        result["closed_episodes"] = closed_episodes
        logger.info("xuchang_station_deviation_alert_completed", alert_count=len(result["alerts"]), target_hour=result["target_hour"])
        return result
