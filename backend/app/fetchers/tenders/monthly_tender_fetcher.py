"""Project-scheduled previous-month Zhiliao ingestion, using the tested CLI."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import json
import os
import sys
from zoneinfo import ZoneInfo

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.utils.path_config import PROJECT_ROOT, get_data_registry, format_agent_path, resolve_agent_path
from config.settings import settings

logger = structlog.get_logger()


def previous_month(today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


class MonthlyTenderInformationFetcher(DataFetcher):
    def __init__(self, today_factory=None, runner=None):
        # Keep the existing project fetcher identity; do not register a second
        # daily job alongside the monthly one.
        super().__init__(
            name="tender_information_fetcher",
            description="知了中标信息：每月月初抓取上月、分类标签并入库（详情按需获取）",
            schedule=settings.tender_monthly_schedule,
            version="2.0.0",
        )
        self.enabled = settings.tender_fetcher_enabled
        self.today_factory = today_factory or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")).date())
        self.runner = runner or self._run_process

    async def fetch_and_store(self):
        if not self.enabled:
            return {"skipped": True}
        start, end = previous_month(self.today_factory())
        # Retry the identical closed interval. Paid pages and saved notices are
        # reused by the CLI; do not recompute dates across a midnight boundary.
        for attempt in range(1, 4):
            try:
                result = await self.runner(start, end)
                logger.info("monthly_tenders_completed", start=str(start), end=str(end), **result)
                return {"start": str(start), "end": str(end), **result}
            except Exception as exc:
                logger.warning("monthly_tenders_attempt_failed", start=str(start), end=str(end),
                               attempt=attempt, error_type=type(exc).__name__)
                if attempt == 3:
                    raise
                await asyncio.sleep(30)

    async def _run_process(self, start, end):
        folder = get_data_registry() / "tenders" / "monthly_runs"
        folder.mkdir(parents=True, exist_ok=True)
        log_path = folder / f"{start}_{end}.log"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
        # This workload runs in a separate process so synchronous ODBC work
        # cannot block the worker's other scheduled tasks.
        with log_path.open("ab") as output:
            phases = [("backfill_zhiliao_month.py", ["--batch-size", "5"]),
                      ("audit_zhiliao_backfill.py", [])]
            for script, extra in phases:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, str(PROJECT_ROOT / "backend/scripts" / script),
                    "--start", str(start), "--end", str(end), *extra,
                    cwd=str(PROJECT_ROOT), env=env,
                    stdout=output, stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    code = await asyncio.wait_for(process.wait(), timeout=6 * 60 * 60)
                finally:
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=20)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                if code:
                    raise RuntimeError(f"{script} failed ({code}); see {format_agent_path(log_path)}")
        strategy = json.loads(resolve_agent_path("backend/app/services/tenders/zhiliao_strategy.json").read_text())
        summary_path = get_data_registry() / "tenders/backfills" / f"{start}_{end}_{strategy['strategy_version']}" / "summary.json"
        summary = json.loads(summary_path.read_text())
        return {"log_path": format_agent_path(log_path), "exit_code": 0,
                "candidates": summary["candidates"], "saved_this_execution": summary["saved_this_execution"],
                "api_cost_units": summary["api_cost_units_this_execution"], "audit_passed": True}
