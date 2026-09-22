"""Migrate scheduled task executions from ``executions.json`` into the database.

Also rebuilds records that the legacy global 50-record cap evicted, using the
per-task memory case log (``scheduled_tasks/memory/<task_id>/cases.jsonl``) plus
the persisted session transcripts, so historical executions reappear in the
execution list.

Usage (inside the backend working directory, with DATABASE_URL configured)::

    python -m app.db.migrate_scheduled_task_executions_to_db --import-json
    python -m app.db.migrate_scheduled_task_executions_to_db --rebuild-missing
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import structlog

from app.scheduled_tasks.models import (
    ExecutionStatus,
    StepExecution,
    TaskExecution,
)
from app.scheduled_tasks.storage.execution_storage_db import DatabaseExecutionStorage
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

_SUCCESS_STATUSES = {"succeeded", "success"}
_FAILED_STATUSES = {"failed", "failure", "error"}


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _scheduled_dir() -> Path:
    return get_data_registry() / "scheduled_tasks"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def import_json_executions(source: Path, storage: DatabaseExecutionStorage) -> int:
    """Upsert every record from the legacy ``executions.json`` file."""
    if not source.is_file():
        logger.warning("executions_json_not_found", path=str(source))
        return 0

    records = _load_json(source)
    imported = 0
    for record in records:
        if not isinstance(record, dict) or not record.get("execution_id"):
            continue
        storage.create(TaskExecution(**record))
        imported += 1
    logger.info("executions_json_imported", source=str(source), imported=imported)
    return imported


def _load_event_claims() -> dict[str, dict]:
    """Map execution_id -> latest event claim row."""
    claims: dict[str, dict] = {}
    claims_dir = _scheduled_dir() / "event_claims"
    if not claims_dir.is_dir():
        return claims
    for path in claims_dir.glob("*.json"):
        try:
            claim = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        execution_id = claim.get("execution_id")
        if not execution_id:
            continue
        current = claims.get(execution_id)
        if current is None or str(claim.get("updated_at") or "") >= str(
            current.get("updated_at") or ""
        ):
            claims[execution_id] = claim
    return claims


async def _load_session_transcripts() -> dict[str, tuple[str, Optional[str]]]:
    """Map scheduled_execution_id -> (session_id, final assistant text)."""
    from sqlalchemy import select

    from app.db.models_session import SessionDB, SessionMessageDB
    from app.db.sync_bridge import session_db_session

    transcripts: dict[str, tuple[str, Optional[str]]] = {}
    async with session_db_session() as session:
        rows = (
            await session.execute(
                select(SessionDB.session_id, SessionDB.session_metadata)
            )
        ).all()
        for session_id, metadata in rows:
            metadata = metadata or {}
            execution_id = metadata.get("scheduled_execution_id")
            if execution_id:
                transcripts[str(execution_id)] = (str(session_id), None)

        if transcripts:
            session_ids = [item[0] for item in transcripts.values()]
            message_rows = (
                await session.execute(
                    select(
                        SessionMessageDB.session_id,
                        SessionMessageDB.content,
                        SessionMessageDB.sequence_number,
                    )
                    .where(
                        SessionMessageDB.session_id.in_(session_ids),
                        SessionMessageDB.msg_type == "final",
                    )
                    .order_by(
                        SessionMessageDB.session_id,
                        SessionMessageDB.sequence_number,
                    )
                )
            ).all()
            finals: dict[str, Any] = {}
            for session_id, content, _ in message_rows:
                finals[str(session_id)] = content
            for execution_id, (session_id, _) in list(transcripts.items()):
                content = finals.get(session_id)
                if content is not None:
                    transcripts[execution_id] = (session_id, str(content))
    return transcripts


def _task_meta_by_id() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    tasks_path = _scheduled_dir() / "tasks.json"
    if not tasks_path.is_file():
        return meta
    try:
        tasks = _load_json(tasks_path)
    except (OSError, json.JSONDecodeError):
        return meta
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks", tasks)
    for task in tasks or []:
        if isinstance(task, dict) and task.get("task_id"):
            meta[str(task["task_id"])] = task
    return meta


def _build_execution(
    *,
    task_id: str,
    case: dict,
    claim: dict,
    session_id: Optional[str],
    final_response: Optional[str],
    task_meta: dict,
) -> TaskExecution:
    status = ExecutionStatus.SUCCESS
    raw_status = str(case.get("status") or claim.get("status") or "").lower()
    if raw_status in _FAILED_STATUSES:
        status = ExecutionStatus.FAILED
    elif raw_status not in _SUCCESS_STATUSES:
        status = ExecutionStatus.FAILED

    started_at = _parse_datetime(case.get("started_at")) or datetime.now()
    duration = case.get("duration_seconds")
    completed_at = (
        started_at + timedelta(seconds=float(duration))
        if duration is not None
        else started_at
    )

    trigger = case.get("trigger") or {}
    attributes = trigger.get("attributes") or {}
    prompt = str(task_meta.get("prompt") or task_meta.get("description") or "")
    step = StepExecution(
        step_id="recovered",
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=float(duration) if duration is not None else None,
        agent_prompt=prompt,
        agent_response=final_response,
        error_message=None if status == ExecutionStatus.SUCCESS else "历史执行失败（自会话记录恢复）",
    )

    return TaskExecution(
        execution_id=str(case["execution_id"]),
        task_id=task_id,
        task_name=str(task_meta.get("name") or task_id),
        session_id=session_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=float(duration) if duration is not None else None,
        steps=[step],
        trigger_type=str(trigger.get("type") or "event"),
        event_id=claim.get("event_id"),
        event_type=str(trigger.get("event_type") or claim.get("event_type") or ""),
        event_attributes=attributes,
        total_steps=1,
        completed_steps=1 if status == ExecutionStatus.SUCCESS else 0,
        failed_steps=0 if status == ExecutionStatus.SUCCESS else 1,
        error_message=None if status == ExecutionStatus.SUCCESS else "历史执行失败（自会话记录恢复）",
    )


def rebuild_missing_from_history(
    storage: DatabaseExecutionStorage,
    *,
    task_ids: Optional[set[str]] = None,
) -> int:
    """Recreate executions recorded in memory cases but absent from storage."""
    from app.db.sync_bridge import run_db

    memory_root = _scheduled_dir() / "memory"
    if not memory_root.is_dir():
        logger.warning("memory_dir_not_found", path=str(memory_root))
        return 0

    claims = _load_event_claims()
    transcripts = run_db(_load_session_transcripts())
    task_meta = _task_meta_by_id()

    rebuilt = 0
    for task_dir in sorted(memory_root.iterdir()):
        cases_path = task_dir / "cases.jsonl"
        if not cases_path.is_file():
            continue
        task_id = task_dir.name
        if task_ids is not None and task_id not in task_ids:
            continue
        for line in cases_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError:
                continue
            execution_id = case.get("execution_id")
            if not execution_id:
                continue
            if storage.get(str(execution_id)) is not None:
                continue
            session_id, final_response = transcripts.get(str(execution_id), (None, None))
            execution = _build_execution(
                task_id=task_id,
                case=case,
                claim=claims.get(str(execution_id), {}),
                session_id=session_id,
                final_response=final_response,
                task_meta=task_meta.get(task_id, {}),
            )
            storage.create(execution)
            rebuilt += 1
            logger.info(
                "execution_rebuilt",
                execution_id=execution_id,
                task_id=task_id,
                status=execution.status.value,
            )
    return rebuilt


async def _ensure_schema_async() -> None:
    """Create the execution table on the sync bridge loop.

    The bridge owns its own engine, and the storage layer writes through the
    same loop, so schema creation stays on one event loop.
    """
    from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB
    from app.db.sync_bridge import session_db_session

    async with session_db_session() as session:
        conn = await session.connection()
        await conn.run_sync(
            ScheduledTaskExecutionDB.__table__.create,
            checkfirst=True,
        )
        await session.commit()


def _ensure_schema() -> None:
    from app.db.sync_bridge import run_db

    run_db(_ensure_schema_async())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executions-json",
        type=Path,
        default=_scheduled_dir() / "executions.json",
        help="Legacy executions.json path (defaults to the data registry).",
    )
    parser.add_argument(
        "--import-json",
        action="store_true",
        help="Import the legacy executions.json into the database.",
    )
    parser.add_argument(
        "--rebuild-missing",
        action="store_true",
        help="Rebuild executions evicted by the old global cap from memory cases.",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Skip creating the target table before writing.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=None,
        help="Limit --rebuild-missing to these task ids (repeatable).",
    )
    args = parser.parse_args()

    if not args.import_json and not args.rebuild_missing:
        args.import_json = True
        args.rebuild_missing = True

    if not args.no_schema:
        _ensure_schema()

    storage = DatabaseExecutionStorage()
    if args.import_json:
        import_json_executions(args.executions_json, storage)
    if args.rebuild_missing:
        rebuilt = rebuild_missing_from_history(
            storage,
            task_ids=set(args.task_id) if args.task_id else None,
        )
        logger.info("executions_rebuilt_total", rebuilt=rebuilt)
    print("done")


if __name__ == "__main__":
    main()
