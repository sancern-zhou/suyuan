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
    write_latest_alert,
)
from app.scenarios.yuncheng_trial.paths import build_alert_run_dir

logger = structlog.get_logger()


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
        alert_path = write_latest_alert(self.registry_root, state)

        manifest_path = None
        if state.get("has_alert") is True and state.get("status") == "pending_trace":
            output_dir = build_alert_run_dir(self.registry_root, str(state["target_time"]))
            manifest_path = await collect_from_alert_file(alert_path=alert_path, output_dir=output_dir)

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
