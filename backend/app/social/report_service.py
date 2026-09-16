"""Persistence and query service for scheduled report results."""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from app.db.database import async_session
from .report_models import SocialReportResult


def report_id_for(execution_id: str, owner_user_id: str) -> str:
    return "report:" + sha256(f"{execution_id}:{owner_user_id}".encode()).hexdigest()[:40]


async def publish_report_results(*, recipients: list[str], task_id: str, execution_id: str,
                                 task_name: str, report_type: str, title: str,
                                 summary: str, attachments: list[dict[str, Any]],
                                 metadata: dict[str, Any] | None = None,
                                 generated_at: datetime | None = None) -> list[str]:
    generated = generated_at or datetime.utcnow()
    ids: list[str] = []
    async with async_session() as session:
        for owner in dict.fromkeys(str(item).strip() for item in recipients if str(item).strip()):
            report_id = report_id_for(execution_id, owner)
            payload = {
                "report_id": report_id, "owner_user_id": owner, "task_id": task_id,
                "execution_id": execution_id, "task_name": task_name,
                "report_type": report_type or "scheduled_report", "title": title or task_name,
                "summary": summary or "", "status": "success", "generated_at": generated,
                "attachments": attachments, "metadata_json": metadata or {}, "updated_at": datetime.utcnow(),
            }
            existing = await session.get(SocialReportResult, report_id)
            if existing is None:
                session.add(SocialReportResult(**payload))
            else:
                for key, value in payload.items():
                    if key not in {"report_id", "owner_user_id", "read", "read_at"}:
                        setattr(existing, key, value)
            ids.append(report_id)
        await session.commit()
    return ids


def report_payload(row: SocialReportResult) -> dict[str, Any]:
    return {
        "report_id": row.report_id, "task_id": row.task_id, "execution_id": row.execution_id,
        "task_name": row.task_name, "report_type": row.report_type, "title": row.title,
        "summary": row.summary, "status": row.status, "generated_at": row.generated_at.isoformat(),
        "read": row.read, "read_at": row.read_at.isoformat() if row.read_at else None,
        "attachments": row.attachments or [], "metadata": row.metadata_json or {},
    }


async def list_report_results(owner_user_id: str, *, limit: int, before: str | None = None,
                              report_type: str | None = None, start_time: datetime | None = None,
                              end_time: datetime | None = None) -> list[SocialReportResult]:
    async with async_session() as session:
        statement = select(SocialReportResult).where(SocialReportResult.owner_user_id == owner_user_id)
        if report_type:
            statement = statement.where(SocialReportResult.report_type == report_type)
        if start_time:
            statement = statement.where(SocialReportResult.generated_at >= start_time)
        if end_time:
            statement = statement.where(SocialReportResult.generated_at <= end_time)
        if before:
            cursor = await session.get(SocialReportResult, before)
            if cursor:
                statement = statement.where(SocialReportResult.generated_at < cursor.generated_at)
        statement = statement.order_by(SocialReportResult.generated_at.desc()).limit(limit)
        return list((await session.execute(statement)).scalars().all())


async def get_report(owner_user_id: str, report_id: str) -> SocialReportResult | None:
    async with async_session() as session:
        statement = select(SocialReportResult).where(
            SocialReportResult.owner_user_id == owner_user_id,
            SocialReportResult.report_id == report_id,
        )
        return (await session.execute(statement)).scalar_one_or_none()


async def mark_report_read(owner_user_id: str, report_id: str | None = None) -> int:
    async with async_session() as session:
        statement = update(SocialReportResult).where(SocialReportResult.owner_user_id == owner_user_id)
        if report_id:
            statement = statement.where(SocialReportResult.report_id == report_id)
        result = await session.execute(statement.values(read=True, read_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        await session.commit()
        return int(result.rowcount or 0)


async def delete_report(owner_user_id: str, report_id: str) -> bool:
    async with async_session() as session:
        result = await session.execute(delete(SocialReportResult).where(
            SocialReportResult.owner_user_id == owner_user_id,
            SocialReportResult.report_id == report_id,
        ))
        await session.commit()
        return bool(result.rowcount)
