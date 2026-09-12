"""Durable catalog for report-package outputs."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.database import async_session
from app.db.report_package_model import ReportPackageDB


def _dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


async def publish_report_meta(meta: dict) -> None:
    """Upsert a report package index entry; callers may safely ignore failures."""
    report_id = str(meta.get("report_id") or "").strip()
    if not report_id:
        return
    now = datetime.now()
    async with async_session() as session:
        entry = await session.get(ReportPackageDB, report_id)
        if entry is None:
            entry = ReportPackageDB(report_id=report_id, created_at=_dt(meta.get("created_at")) or now)
            session.add(entry)
        entry.title = str(meta.get("title") or report_id)
        entry.report_type = str(meta.get("report_type") or meta.get("source") or "other")
        entry.source = str(meta.get("source") or "")
        entry.task_id = meta.get("task_id")
        entry.execution_id = meta.get("execution_id")
        entry.period_start = _dt(meta.get("period_start"))
        entry.period_end = _dt(meta.get("period_end"))
        entry.status = str(meta.get("status") or "published")
        entry.version = int(meta.get("version") or 1)
        entry.files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        entry.extra_metadata = {k: v for k, v in meta.items() if k not in {"files"}}
        entry.updated_at = _dt(meta.get("updated_at")) or now
        await session.commit()


async def list_report_packages(*, report_type=None, format_name=None, start_time=None, end_time=None):
    async with async_session() as session:
        result = await session.execute(select(ReportPackageDB).order_by(ReportPackageDB.updated_at.desc()))
        entries = list(result.scalars())
    start = _dt(start_time)
    end = _dt(end_time)
    output = []
    for entry in entries:
        files = entry.files if isinstance(entry.files, dict) else {}
        if report_type and entry.report_type != report_type:
            continue
        if format_name and format_name not in files:
            continue
        if start and entry.updated_at and entry.updated_at < start:
            continue
        if end and entry.updated_at and entry.updated_at > end:
            continue
        output.append(entry)
    return output
