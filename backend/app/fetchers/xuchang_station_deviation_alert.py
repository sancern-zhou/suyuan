"""Hourly deterministic trigger for the Xuchang Scenario 1 Agent workflow."""

from __future__ import annotations

from datetime import datetime, timedelta
from time import perf_counter
from typing import TYPE_CHECKING, Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_station_deviation.evidence import (
    XuchangStationDeviationEvidenceCollector,
)
from app.scenarios.xuchang_station_deviation.service import (
    EVENT_TYPE,
    XuchangStationDeviationAlertService,
)
from app.scenarios.xuchang_transport_escalation import (
    ESCALATED_EVENT_TYPE,
    XuchangTransportEscalationService,
)
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path

if TYPE_CHECKING:
    from app.tools.analysis.xuchang_upwind_permit_sources.tool import (
        AnalyzeXuchangUpwindPermitSourcesTool,
    )


logger = structlog.get_logger()
SCENARIO_1_SLA_MS = 5_000
POLLUTANT_ANALYSIS_PROFILES = {
    "PM2.5": {"lookback_hours": 1, "candidate_radius_km": 10.0},
    "O3": {"lookback_hours": 2, "candidate_radius_km": 20.0},
    "NOX": {"lookback_hours": 0, "candidate_radius_km": 5.0},
}


class XuchangStationDeviationAlertFetcher(DataFetcher):
    def __init__(
        self,
        service: XuchangStationDeviationAlertService | None = None,
        analysis_tool: AnalyzeXuchangUpwindPermitSourcesTool | None = None,
        escalation_service: XuchangTransportEscalationService | None = None,
        evidence_collector: XuchangStationDeviationEvidenceCollector | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_station_deviation_alert_fetcher",
            description="许昌场景一站点空间偏差阈值告警",
            schedule="15 * * * *",
            version="1.0.0",
        )
        self.service = service or XuchangStationDeviationAlertService()
        if analysis_tool is None:
            # Deferred to avoid importing a tool through app.fetchers during
            # package initialization.
            from app.tools.analysis.xuchang_upwind_permit_sources.tool import (
                AnalyzeXuchangUpwindPermitSourcesTool,
            )

            analysis_tool = AnalyzeXuchangUpwindPermitSourcesTool()
        self.analysis_tool = analysis_tool
        self.escalation_service = escalation_service or XuchangTransportEscalationService()
        self.evidence_collector = evidence_collector or XuchangStationDeviationEvidenceCollector()

    async def fetch_and_store(self) -> dict[str, Any]:
        result = await self.service.run()
        if result["alerts"]:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
            for alert in result["alerts"]:
                started = perf_counter()
                profile = POLLUTANT_ANALYSIS_PROFILES[alert["target_pollutant"]]
                event_hour = datetime.fromisoformat(alert["occurred_at"])
                analysis_start = event_hour - timedelta(hours=profile["lookback_hours"])
                try:
                    analysis = await self.analysis_tool.execute(
                        station_name=alert["station_name"],
                        lat=alert["lat"],
                        lon=alert["lon"],
                        pollutant=alert["target_pollutant"],
                        start_time=analysis_start.isoformat(),
                        end_time=alert["occurred_at"],
                        candidate_radius_km=profile["candidate_radius_km"],
                        event_context=alert,
                    )
                except Exception as exc:
                    logger.exception("xuchang_scenario_1_source_screening_failed", event_id=alert["event_id"])
                    analysis = {"status": "failed", "error": str(exc)}
                elapsed_ms = round((perf_counter() - started) * 1000)
                analysis_data = analysis.get("data") if isinstance(analysis.get("data"), dict) else analysis
                scenario_output = analysis_data.get("scenario_1_output")
                if scenario_output:
                    scenario_output["response_time_ms"] = elapsed_ms
                    scenario_output["sla_target_ms"] = SCENARIO_1_SLA_MS
                    scenario_output["sla_met"] = elapsed_ms <= SCENARIO_1_SLA_MS
                    output_path = self.service.write_scenario_output(alert, scenario_output)
                    alert["scenario_1_output"] = scenario_output
                    alert["scenario_1_output_path"] = format_agent_path(output_path)
                alert["source_screening_status"] = analysis.get("status")
                alert["source_screening_response_time_ms"] = elapsed_ms
                alert["source_screening_sla_met"] = elapsed_ms <= SCENARIO_1_SLA_MS
                try:
                    evidence = await self.evidence_collector.collect(
                        alert=alert,
                        source_screening=analysis,
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
                escalation = self.escalation_service.ingest_scenario_1_alert(alert)
                escalation_job = escalation.get("job") or {}
                alert["scenario_2_escalation"] = {
                    "status": escalation["status"],
                    "process_id": escalation.get("process", {}).get("process_id"),
                    "job_id": escalation_job.get("job_id"),
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
                if escalation.get("job"):
                    job = escalation["job"]
                    await task_service.publish_event(TaskEvent(
                        event_id=job["event_id"],
                        event_type=ESCALATED_EVENT_TYPE,
                        occurred_at=alert["occurred_at"],
                        attributes={
                            "city": job["city"],
                            "target_pollutant": job["target_pollutant"],
                            "station_id": job["station_id"],
                        },
                        payload=job,
                    ))
        logger.info("xuchang_station_deviation_alert_completed", alert_count=len(result["alerts"]), target_hour=result["target_hour"])
        return result
