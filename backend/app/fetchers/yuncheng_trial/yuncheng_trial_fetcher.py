"""Fetcher for the Yuncheng trial hourly watch scenario."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.yuncheng_trial.collect_tracing_context import collect_from_alert_file
from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG
from app.scenarios.yuncheng_trial.fetch_and_alert import (
    evaluate_alert_rules,
    fetch_target_city_hourly_rows,
    write_alert_evidence,
)

logger = structlog.get_logger()


async def publish_task_event(event) -> None:
    """Publish through the task service without importing it on silent runs."""
    from app.scheduled_tasks import get_scheduled_task_service

    await get_scheduled_task_service().publish_event(event)


class YunchengTrialFetcher(DataFetcher):
    """Run Yuncheng city-level watch alerts and collect tracing context on alert."""

    DEFAULT_HOURS = YUNCHENG_TRIAL_CONFIG.default_lookback_hours

    def __init__(self, registry_root: Path | None = None, hours: int = DEFAULT_HOURS):
        super().__init__(
            name="yuncheng_trial_fetcher",
            description="运城市驻场试用场景小时数据盯守与告警后溯源上下文抓取",
            schedule="0 * * * *",
            version="1.0.0",
        )
        self.registry_root = registry_root or Path(__file__).resolve().parents[3] / "backend_data_registry"
        self.hours = hours

    async def fetch_and_store(self) -> dict[str, Any]:
        end_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        rows = fetch_target_city_hourly_rows(
            city=YUNCHENG_TRIAL_CONFIG.city,
            end_time=end_time,
            hours=self.hours,
        )
        state = evaluate_alert_rules(rows)
        alert_path = write_alert_evidence(self.registry_root, state)

        manifest_path = None
        if state.get("has_alert") is True and state.get("status") == "pending_trace":
            manifest_path = await collect_from_alert_file(alert_path=alert_path, output_dir=alert_path.parent)
            if manifest_path and Path(manifest_path).is_file():
                from app.scheduled_tasks.models.event import TaskEvent

                await publish_task_event(TaskEvent(
                    event_id=str(state["alert_id"]),
                    event_type="yuncheng.alert.created",
                    occurred_at=state["checked_at"],
                    attributes={
                        "city": state["city"],
                        "alert_level": state.get("alert_level"),
                        "target_pollutant": state.get("target_pollutant"),
                    },
                    payload={
                        "alert_json_path": str(alert_path),
                        "tracing_context_manifest_path": str(manifest_path),
                        "evidence_dir": str(alert_path.parent),
                    },
                ))

        logger.info(
            "yuncheng_trial_fetcher_completed",
            city=YUNCHENG_TRIAL_CONFIG.city,
            has_alert=state.get("has_alert"),
            status=state.get("status"),
            alert_path=str(alert_path),
            manifest_path=str(manifest_path) if manifest_path else None,
            rows=len(rows),
        )

        return {
            "city": YUNCHENG_TRIAL_CONFIG.city,
            "has_alert": state.get("has_alert"),
            "status": state.get("status"),
            "alert_path": str(alert_path),
            "manifest_path": str(manifest_path) if manifest_path else None,
            "rows": len(rows),
        }
