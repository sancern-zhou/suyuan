"""Backfill structured scheduled task results into the database.

Builds one ``scheduled_task_results`` row per execution from the existing
``scheduled_task_executions`` documents, enriching each row with the distilled
case (city/station/pollutant/conclusion/findings) from the per-task case log
(``scheduled_tasks/memory/<task_id>/cases.jsonl``) when available.

Usage (inside the backend working directory, with DATABASE_URL configured)::

    python -m app.db.backfill_scheduled_task_results [--task-id ID ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import structlog

from app.db.models import scheduled_task_execution_db  # noqa: F401
from app.db.models import scheduled_task_result_db  # noqa: F401
from app.scheduled_tasks.models import ExecutionStatus, TaskExecution
from app.scheduled_tasks.models.result import TaskResult
from app.scheduled_tasks.storage.task_result_storage_db import (
    DatabaseTaskResultStorage,
    task_result_db_enabled,
)
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()


def _load_cases_by_execution(task_id: str) -> dict[str, dict[str, Any]]:
    """Load the task's case log keyed by execution id (best effort)."""
    path = get_data_registry() / "scheduled_tasks" / "memory" / task_id / "cases.jsonl"
    cases: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return cases
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except ValueError:
            continue
        execution_id = case.get("execution_id")
        if isinstance(execution_id, str):
            cases[execution_id] = case
    return cases


def _agent_material_from_execution(execution: TaskExecution) -> dict[str, Any]:
    """Rebuild the executor's ``collected`` materials from stored steps."""
    visuals: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    for step in execution.steps:
        visuals.extend(visual for visual in step.result_visuals if isinstance(visual, dict))
        for call in step.tool_calls:
            if isinstance(call, dict):
                tool_calls.append(call)
    return {"visuals": visuals, "tool_calls": tool_calls}


def _event_for_execution(execution: TaskExecution) -> Optional[Any]:
    if not execution.event_id:
        return None

    class _Shim:  # 最小事件视图：仅 attributes/payload 参与维度兜底
        event_id = execution.event_id
        event_type = execution.event_type
        attributes = dict(execution.event_attributes or {})
        payload: dict[str, Any] = {}

    return _Shim()


def build_task_result(execution: TaskExecution, case: Optional[dict]) -> TaskResult:
    from app.scheduled_tasks.result_extraction import extract_task_result

    return extract_task_result(
        execution=execution,
        event=_event_for_execution(execution),
        agent_result=_agent_material_from_execution(execution),
        case=case,
    )


class _EvidenceResolver:
    """Resolve evidence packages for alert executions by station and time.

    Evidence file names embed the alert minute and station
    (``xuchang-station-episode-{YYYYMMDDHHMM}-{station}-{hash}.evidence.json``)
    and are written at event publish time, so the execution's start time plus
    station id identify the package. Silent no-op when the evidence root does
    not exist (other deployments).
    """

    _FILE_PATTERN = re.compile(
        r"^xuchang-station-episode-(?P<moment>\d{12})-(?P<station>.+)-[0-9a-f]+\.evidence\.json$"
    )
    _TOLERANCE_SECONDS = 7200

    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = evidence_root
        self._day_cache: dict[Any, list[tuple[str, str, str]]] = {}

    def _day_files(self, day) -> list[tuple[str, str, str]]:
        if day not in self._day_cache:
            day_dir = self.evidence_root / day.strftime("%Y%m%d")
            try:
                names = sorted(path.name for path in day_dir.glob("*.evidence.json"))
            except OSError:
                names = []
            parsed = []
            for name in names:
                match = self._FILE_PATTERN.match(name)
                if match:
                    parsed.append((name, match["moment"], match["station"]))
            self._day_cache[day] = parsed
        return self._day_cache[day]

    def resolve(self, execution: TaskExecution, station_id: Optional[str]) -> Optional[str]:
        station = str(
            station_id or (execution.event_attributes or {}).get("station_id") or ""
        )
        occurred = execution.started_at
        if not station or occurred is None:
            return None
        target = occurred.date()
        best: tuple[float, str] | None = None
        for offset in (-1, 0, 1):
            day = target + timedelta(days=offset)
            for name, moment, file_station in self._day_files(day):
                if file_station != station:
                    continue
                file_time = datetime.strptime(moment, "%Y%m%d%H%M")
                delta = abs((file_time - occurred).total_seconds())
                if delta > self._TOLERANCE_SECONDS:
                    continue
                path = format_agent_path(self.evidence_root / day.strftime("%Y%m%d") / name)
                if best is None or delta < best[0]:
                    best = (delta, path)
        return best[1] if best else None


def backfill(
    storage: DatabaseTaskResultStorage,
    task_ids: Optional[list[str]] = None,
    dry_run: bool = False,
    resolve_evidence: bool = True,
) -> int:
    from app.db.sync_bridge import bridge_session, run_db
    from sqlalchemy import select

    from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB

    evidence_root = get_data_registry() / "xuchang_station_deviation_alerts"
    resolver = _EvidenceResolver(evidence_root) if resolve_evidence and evidence_root.is_dir() else None

    conditions = []
    if task_ids:
        conditions.append(ScheduledTaskExecutionDB.task_id.in_(task_ids))

    async def _collect():
        async with bridge_session() as session:
            stmt = select(ScheduledTaskExecutionDB).order_by(
                ScheduledTaskExecutionDB.started_at.asc()
            )
            if conditions:
                stmt = stmt.where(*conditions)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                TaskExecution(**row.data)
                for row in rows
                if row.status != ExecutionStatus.RUNNING.value
            ]

    executions = run_db(_collect())
    written = 0
    for execution in executions:
        cases = _load_cases_by_execution(execution.task_id)
        case = cases.get(execution.execution_id)
        result = build_task_result(execution, case)
        if resolver is not None and not result.evidence_package_paths:
            path = resolver.resolve(execution, result.station_id)
            if path:
                result.evidence_package_paths = [path]
        if dry_run:
            logger.info(
                "task_result_backfill_dry_run",
                execution_id=execution.execution_id,
                task_id=execution.task_id,
                city=result.city,
                station=result.station_name or result.station_id,
                pollutant=result.pollutant,
                conclusion=(result.conclusion or "")[:50],
                images=len(result.image_paths),
                documents=len(result.document_paths),
            )
        else:
            storage.upsert(result)
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-id",
        action="append",
        help="Limit the backfill to these task ids (repeatable).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and log results without writing to the database.",
    )
    args = parser.parse_args()

    if not task_result_db_enabled():
        raise SystemExit("DATABASE_URL is not configured; nothing to backfill.")

    written = backfill(
        DatabaseTaskResultStorage(),
        task_ids=args.task_id,
        dry_run=args.dry_run,
    )
    logger.info("task_result_backfill_done", written=written, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
