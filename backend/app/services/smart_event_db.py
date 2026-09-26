"""Database-primary persistence for smart events.

Events and task cards live in PostgreSQL as JSONB documents with a small set
of promoted, indexed columns for filtering and sorting. Evidence packages stay
on the filesystem: the heavy ``sources`` payload is written to an immutable
content-addressed file and the database keeps only a lightweight stub.
"""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.utils.path_config import get_data_registry

ADVISORY_LOCK_KEY = "jiangsu_smart_event_store"
_STORE_KEYS = {"events", "tasks", "schema_version"}


def smart_event_db_enabled() -> bool:
    configured = os.getenv("SMART_EVENT_STORAGE")
    if configured:
        return configured.strip().lower() != "file"
    return bool(os.getenv("DATABASE_URL"))


def _packages():
    from app.services.jiangsu_smart_event_store import JiangsuEventPackages

    return JiangsuEventPackages(get_data_registry() / "jiangsu_smart_events" / "store.json")


def _parse_db_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None
    if parsed.tzinfo is not None:
        # 智能事件库时间列均为 timestamp without time zone，asyncpg 拒绝带时区值，
        # 落库前统一折算为本地裸时间（与 task_review._parse_db_datetime 保持一致）。
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _event_row_values(event: dict, *, include_evidence: bool) -> dict:
    package = event.get("evidence_package") if isinstance(event.get("evidence_package"), dict) else {}
    document = dict(event)
    document.pop("_evidence_lazy", None)
    if include_evidence:
        document.pop("evidence", None)
    values = {
        "event_id": str(event.get("event_id", "")),
        "data": document,
        "event_status": event.get("event_status"),
        "event_type": event.get("event_type"),
        "ai_event_type": event.get("ai_event_type"),
        "ai_suggested_level": event.get("ai_suggested_level"),
        "site_id": event.get("site_id"),
        "site_name": event.get("site_name"),
        "event_name": event.get("event_name"),
        "initial_event_name": event.get("initial_event_name"),
        "primary_clue_tag": event.get("primary_clue_tag"),
        "source_alarm_rule_type": event.get("source_alarm_rule_type"),
        "latest_occurrence_time": _parse_db_datetime(event.get("latest_occurrence_time")),
        "event_start_time": _parse_db_datetime(event.get("event_start_time")),
        "created_at": _parse_db_datetime(event.get("created_at")),
        "updated_at": _parse_db_datetime(event.get("updated_at")),
        "archived": bool(event.get("archived", False)),
        "evidence_package_path": package.get("persisted_path"),
    }
    if include_evidence:
        values["evidence"] = event.get("evidence")
    return values


def _task_row_values(task: dict) -> dict:
    return {
        "task_id": str(task.get("task_id", "")),
        "data": task,
        "event_id": str(task.get("event_id", "")),
        "status": task.get("status"),
        "scheduled_task_id": task.get("scheduled_task_id"),
        "created_at": _parse_db_datetime(task.get("created_at")),
        "updated_at": _parse_db_datetime(task.get("updated_at")),
    }


async def load_store_async(event_ids=None) -> dict:
    from app.db.models.smart_event_db import SmartEventDB, SmartEventStateDB, SmartEventTaskDB
    from app.db.sync_bridge import bridge_session
    from app.services.jiangsu_smart_event_store import SCHEMA, StoreSnapshot

    async with bridge_session() as session:
        if event_ids is None:
            event_stmt = select(SmartEventDB.data, SmartEventDB.event_id).order_by(
                SmartEventDB.updated_at.desc().nullslast())
            events = [{**row[0], "_evidence_lazy": True} for row in (await session.execute(event_stmt)).all()]
        else:
            event_stmt = select(SmartEventDB.data, SmartEventDB.evidence).where(
                SmartEventDB.event_id.in_(event_ids)).order_by(SmartEventDB.updated_at.desc().nullslast())
            events = [{**row[0], **({"evidence": row[1]} if row[1] is not None else {})}
                      for row in (await session.execute(event_stmt)).all()]
        task_stmt = select(SmartEventTaskDB).order_by(SmartEventTaskDB.created_at.desc().nullslast())
        if event_ids is not None:
            task_stmt = task_stmt.where(SmartEventTaskDB.event_id.in_(event_ids))
        tasks = [row.data for row in (await session.execute(task_stmt)).scalars()]
        state = {row.key: row.value for row in (await session.execute(select(SmartEventStateDB))).scalars()}
    value = {**state, "schema_version": SCHEMA, "events": events, "tasks": tasks}
    return StoreSnapshot(value, deepcopy(value))


async def save_store_async(store) -> dict:
    from app.db.models.smart_event_db import SmartEventDB, SmartEventStateDB, SmartEventTaskDB
    from app.db.sync_bridge import bridge_session
    from app.services.jiangsu_smart_event_store import EventStoreConflict

    packages = _packages()
    events = [item for item in store.get("events", []) if isinstance(item, dict) and item.get("event_id")]
    tasks = [item for item in store.get("tasks", []) if isinstance(item, dict) and item.get("task_id")]
    for event in events:
        packages.write_evidence_only(event)
    base = getattr(store, "base", None)
    base_events = {str(item.get("event_id")): item for item in (base or {}).get("events", [])
                   if isinstance(item, dict)}
    base_tasks = {str(item.get("task_id")): item for item in (base or {}).get("tasks", [])
                  if isinstance(item, dict)}

    async with bridge_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SELECT pg_advisory_xact_lock(hashtext('{ADVISORY_LOCK_KEY}'))"))
            if base is not None:
                proposed_ids = {str(item["event_id"]) for item in events}
                check_ids = [eid for eid, item in base_events.items()
                             if eid in proposed_ids and item != next(e for e in events if str(e["event_id"]) == eid)]
                if check_ids:
                    current = {row[0]: row[1] for row in (await session.execute(
                        select(SmartEventDB.event_id, SmartEventDB.updated_at)
                        .where(SmartEventDB.event_id.in_(check_ids)))).all()}
                    for eid in check_ids:
                        if current.get(eid) is None:
                            continue
                        if _parse_db_datetime(base_events[eid].get("updated_at")) != current[eid]:
                            raise EventStoreConflict(f"concurrent_smart_event_update:{eid}")
                for eid in set(base_events) - {str(item["event_id"]) for item in events}:
                    await session.execute(delete(SmartEventDB).where(SmartEventDB.event_id == eid))
                for tid in set(base_tasks) - {str(item["task_id"]) for item in tasks}:
                    await session.execute(delete(SmartEventTaskDB).where(SmartEventTaskDB.task_id == tid))

            with_evidence = [item for item in events if "evidence" in item]
            without_evidence = [item for item in events if "evidence" not in item]
            for group, include in ((with_evidence, True), (without_evidence, False)):
                for chunk_start in range(0, len(group), 100):
                    chunk = [_event_row_values(item, include_evidence=include)
                             for item in group[chunk_start:chunk_start + 100]]
                    stmt = pg_insert(SmartEventDB).values(chunk)
                    update_keys = [key for key in chunk[0] if key != "event_id"]
                    if not include:
                        update_keys = [key for key in update_keys if key != "evidence"]
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["event_id"],
                        set_={key: stmt.excluded[key] for key in update_keys},
                    )
                    await session.execute(stmt)
            for chunk_start in range(0, len(tasks), 200):
                chunk = [_task_row_values(item) for item in tasks[chunk_start:chunk_start + 200]]
                stmt = pg_insert(SmartEventTaskDB).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["task_id"],
                    set_={key: stmt.excluded[key] for key in chunk[0] if key != "task_id"},
                )
                await session.execute(stmt)
            for key, value in store.items():
                if key in _STORE_KEYS or not isinstance(value, (dict, list, str, int, float, bool)):
                    continue
                stmt = pg_insert(SmartEventStateDB).values(key=key, value=value)
                stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": stmt.excluded.value})
                await session.execute(stmt)
    return {"events": len(events), "tasks": len(tasks)}


def _time_column(model):
    return func.coalesce(model.latest_occurrence_time, model.event_start_time)


async def query_events_overview_async(
    *,
    start_time=None,
    end_time=None,
    station_codes=None,
    status=None,
    keyword=None,
    event_type=None,
    event_types=None,
    level=None,
    limit=100,
    offset=0,
) -> dict:
    from sqlalchemy import and_, case, distinct, or_

    from app.db.models.smart_event_db import SmartEventDB, SmartEventStateDB
    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        clauses = []
        review_join = None
        time_col = _time_column(SmartEventDB)
        window_clause = []
        if start_time is not None:
            window_clause.append(time_col >= start_time)
        if end_time is not None:
            window_clause.append(time_col <= end_time)
        if window_clause:
            clauses.append(or_(time_col.is_(None), and_(*window_clause)))
        if station_codes:
            clauses.append(SmartEventDB.site_id.in_(station_codes))
        if status:
            # 归档/退回后有效状态由 task_reviews 决定，smart_events.event_status
            # 列可能滞后；过滤按有效状态进行，与 _with_review_states 保持一致。
            review_join = TaskReviewDB
            effective_status = case(
                (or_(SmartEventDB.archived.is_(True),
                     SmartEventDB.event_status == "已归档",
                     TaskReviewDB.status == "archived"), "已归档"),
                (and_(TaskReviewDB.status == "in_disposal",
                      or_(SmartEventDB.event_status.is_(None),
                          SmartEventDB.event_status != "已反馈")), "待反馈"),
                (TaskReviewDB.status == "rejected", "待复核"),
                else_=SmartEventDB.event_status,
            )
            clauses.append(effective_status == status)
        type_values = [str(item).strip() for item in (event_types or []) if str(item).strip()]
        if type_values:
            clauses.append(func.coalesce(SmartEventDB.ai_event_type, SmartEventDB.event_type).in_(type_values))
        elif event_type:
            clauses.append(func.coalesce(SmartEventDB.ai_event_type, SmartEventDB.event_type) == event_type)
        if level:
            clauses.append(SmartEventDB.ai_suggested_level == level)
        if keyword:
            needle = keyword.strip().lower()
            pattern = f"%{needle}%"
            clauses.append(or_(
                SmartEventDB.event_id.ilike(pattern),
                SmartEventDB.event_name.ilike(pattern),
                SmartEventDB.initial_event_name.ilike(pattern),
                SmartEventDB.site_name.ilike(pattern),
                SmartEventDB.site_id.ilike(pattern),
                SmartEventDB.primary_clue_tag.ilike(pattern),
                SmartEventDB.source_alarm_rule_type.ilike(pattern),
            ))
        where = and_(*clauses) if clauses else None

        count_stmt = select(func.count(SmartEventDB.event_id))
        event_stmt = select(SmartEventDB.data)
        if review_join is not None:
            join_condition = SmartEventDB.data["review_id"].astext == TaskReviewDB.review_id
            count_stmt = count_stmt.outerjoin(review_join, join_condition)
            event_stmt = event_stmt.outerjoin(review_join, join_condition)
        total = (await session.execute(count_stmt.where(where))).scalar_one()
        stmt = event_stmt.where(where)
        stmt = stmt.order_by(_time_column(SmartEventDB).desc().nullslast()).offset(offset).limit(limit)
        events = [row[0] for row in (await session.execute(stmt)).all()]

        stats_total = (await session.execute(
            select(func.count(SmartEventDB.event_id))
        )).scalar_one()
        pending = (await session.execute(
            select(func.count(SmartEventDB.event_id)).where(
                func.coalesce(SmartEventDB.data["ai_judgment"]["final_response"].astext, "") == ""
            )
        )).scalar_one()
        stations = (await session.execute(
            select(func.count(distinct(SmartEventDB.site_id)))
        )).scalar_one()
        statuses = sorted({row for row in (await session.execute(
            select(SmartEventDB.event_status).where(SmartEventDB.event_status.isnot(None))
        )).scalars()})
        types = sorted({row for row in (await session.execute(
            select(func.coalesce(SmartEventDB.ai_event_type, SmartEventDB.event_type))
        )).scalars() if row})
        levels = sorted({row for row in (await session.execute(
            select(SmartEventDB.ai_suggested_level).where(SmartEventDB.ai_suggested_level.isnot(None))
        )).scalars() if row})
        last_sync_row = (await session.execute(
            select(SmartEventStateDB.value).where(SmartEventStateDB.key == "last_sync")
        )).scalar_one_or_none()
    return {
        "events": events,
        "total": total,
        "stats": {"total": stats_total, "pending": pending, "stations": stations},
        "filters": {"statuses": statuses, "types": types, "levels": levels},
        "last_sync": last_sync_row,
    }


async def load_evidence_async(event_ids: list[str]) -> dict[str, dict]:
    """Fetch the heavy legacy evidence payloads for the given events."""
    from app.db.models.smart_event_db import SmartEventDB
    from app.db.sync_bridge import bridge_session

    if not event_ids:
        return {}
    async with bridge_session() as session:
        rows = (await session.execute(
            select(SmartEventDB.event_id, SmartEventDB.evidence)
            .where(SmartEventDB.event_id.in_(event_ids), SmartEventDB.evidence.isnot(None))
        )).all()
        return {row[0]: row[1] for row in rows}


async def list_tasks_async(*, event_id=None, status=None, limit=100) -> list[dict]:
    from app.db.models.smart_event_db import SmartEventTaskDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        stmt = select(SmartEventTaskDB.data)
        if event_id:
            stmt = stmt.where(SmartEventTaskDB.event_id == event_id)
        if status:
            stmt = stmt.where(SmartEventTaskDB.status == status)
        stmt = stmt.order_by(SmartEventTaskDB.created_at.desc()).limit(limit)
        return [row[0] for row in (await session.execute(stmt)).all()]


async def list_ai_judgment_card_refs_async() -> list[dict]:
    """轻量列出 AI 研判卡（不加载事件正文），用于人工退回升量派发。"""
    from sqlalchemy import func, select

    from app.db.models.smart_event_db import SmartEventTaskDB
    from app.db.sync_bridge import bridge_session

    feedback = func.jsonb_extract_path_text(SmartEventTaskDB.data, "continuity", "feedback")
    task_type = func.jsonb_extract_path_text(SmartEventTaskDB.data, "task_type")
    stmt = select(
        SmartEventTaskDB.event_id, SmartEventTaskDB.task_id, SmartEventTaskDB.status, feedback,
    ).where(task_type == "ai_judgment")
    async with bridge_session() as session:
        rows = (await session.execute(stmt)).all()
    return [
        {"event_id": row[0], "task_id": row[1], "status": row[2], "human": row[3] is not None}
        for row in rows
    ]


async def get_task_by_id_async(task_id: str) -> dict | None:
    from app.db.models.smart_event_db import SmartEventTaskDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        return (await session.execute(
            select(SmartEventTaskDB.data).where(SmartEventTaskDB.task_id == task_id)
        )).scalar_one_or_none()


async def get_evidence_path_async(event_id: str) -> str | None:
    from app.db.models.smart_event_db import SmartEventDB
    from app.db.sync_bridge import bridge_session
    from app.utils.path_config import resolve_agent_path

    async with bridge_session() as session:
        path = (await session.execute(
            select(SmartEventDB.evidence_package_path).where(SmartEventDB.event_id == event_id)
        )).scalar_one_or_none()
    if path and resolve_agent_path(path).is_file():
        return path
    return None


async def import_store_from_files_async() -> dict:
    """One-time import of the legacy manifest/packages store into the database."""
    from app.db.models.smart_event_db import SmartEventDB, SmartEventStateDB, SmartEventTaskDB
    from app.db.sync_bridge import bridge_session
    from app.services.jiangsu_smart_event_store import SCHEMA

    packages = _packages()
    manifest = packages.read_manifest()
    events, tasks = [], []
    for row in manifest.get("events", []):
        if not isinstance(row, dict) or not row.get("event_id"):
            continue
        event = packages.read_event(row) if row.get("_detail_ref") else dict(row)
        packages.write_evidence_only(event)
        events.append(event)
    tasks = [dict(item) for item in manifest.get("tasks", []) if isinstance(item, dict) and item.get("task_id")]

    async with bridge_session() as session:
        await session.execute(
            text("DROP TABLE IF EXISTS smart_events, smart_event_tasks, smart_event_state CASCADE"))
        await session.commit()

    from app.db.database import Base

    async with bridge_session() as session:
        bridge_engine = session.bind
        async with bridge_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all,
                                tables=[SmartEventDB.__table__, SmartEventTaskDB.__table__, SmartEventStateDB.__table__])

    store = {**{k: v for k, v in manifest.items() if k not in {"events", "tasks"}},
             "schema_version": SCHEMA, "events": events, "tasks": tasks}
    result = await save_store_async(store)
    return {"imported_events": result["events"], "imported_tasks": result["tasks"]}
