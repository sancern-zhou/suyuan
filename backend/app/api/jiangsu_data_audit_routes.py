"""AI 审核结论查询接口（江苏数据审核复核）。

供平台侧/前端按站点、审核日查询 ``jiangsu_data_audit_review`` 任务的 AI
审核结论及其平台人工反馈状态。数据来自统一 task_review 存储，结论以
``submit_task_review`` 的结构化提交为准，不解析会话回复。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services.task_review import list_reviews, load_review

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/jiangsu/data-audit", tags=["jiangsu-data-audit"])

REVIEW_TASK_ID = "jiangsu_data_audit_review"
_REVIEW_STATUS_VALUES = {
    "pending_review", "in_disposal", "archived", "rejected",
}
_DECISION_VALUES = {"approve", "reject", "needs_evidence", "needs_action"}


def _section_value(record: dict[str, Any], key: str) -> str | None:
    for section in record.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for field in section.get("fields") or []:
            if isinstance(field, dict) and field.get("key") == key:
                value = field.get("value")
                if value not in (None, ""):
                    return str(value)
    return None


def _parse_subject(subject_id: str) -> tuple[str, str | None]:
    code, _, day = str(subject_id or "").partition(":")
    return code.strip(), day.strip() if day else None


def _parse_date_param(value: str | None, field: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} 必须是 YYYY-MM-DD") from exc


def _summary_item(record: dict[str, Any]) -> dict[str, Any]:
    station_code, audit_day = _parse_subject(record.get("subject_id") or "")
    human_decision = record.get("human_decision") or {}
    return {
        "review_id": record.get("review_id"),
        "subject_id": record.get("subject_id"),
        "station_code": station_code or _section_value(record, "station_code"),
        "station_name": _section_value(record, "station_name"),
        "city_name": _section_value(record, "city_name"),
        "audit_day": audit_day or _section_value(record, "audit_day"),
        "task_id": record.get("task_id"),
        "title": record.get("title"),
        "summary": record.get("summary"),
        "decision": record.get("decision"),
        "comment": record.get("comment"),
        "status": record.get("status"),
        "version": record.get("version"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "data_impact_count": len(record.get("data_impact") or []),
        "checks_count": len(record.get("checks") or []),
        "human_decision": {
            "action": human_decision.get("action"),
            "decision": human_decision.get("decision"),
            "comment": human_decision.get("comment"),
            "actor": human_decision.get("actor"),
            "occurred_at": human_decision.get("occurred_at"),
        } if human_decision else None,
        "human_feedback_status": (record.get("human_feedback") or {}).get("status"),
    }


def _detail_item(record: dict[str, Any]) -> dict[str, Any]:
    item = _summary_item(record)
    item.update({
        "submission": record.get("submission"),
        "checks": record.get("checks"),
        "data_impact": record.get("data_impact"),
        "actions": record.get("actions"),
        "sections": record.get("sections"),
        "review_basis": record.get("review_basis"),
        "evidence": record.get("evidence"),
        "history_versions": len(record.get("history") or []),
    })
    return item


@router.get("/conclusions")
async def list_data_audit_conclusions(
    station_code: str | None = Query(default=None, max_length=64),
    city_name: str | None = Query(default=None, max_length=64),
    start_date: str | None = Query(default=None, description="审核日起（YYYY-MM-DD，含）"),
    end_date: str | None = Query(default=None, description="审核日止（YYYY-MM-DD，含）"),
    decision: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    if decision is not None and decision not in _DECISION_VALUES:
        raise HTTPException(status_code=422, detail="decision 取值不合法")
    if status is not None and status not in _REVIEW_STATUS_VALUES:
        raise HTTPException(status_code=422, detail="status 取值不合法")
    start_day = _parse_date_param(start_date, "start_date")
    end_day = _parse_date_param(end_date, "end_date")
    if start_day and end_day and end_day < start_day:
        raise HTTPException(status_code=422, detail="end_date 不能早于 start_date")

    records = list_reviews(pending_only=False, task_id=REVIEW_TASK_ID)
    items: list[dict[str, Any]] = []
    wanted_station = station_code.strip() if station_code else None
    wanted_city = city_name.strip() if city_name else None
    for record in records:
        item = _summary_item(record)
        if wanted_station and str(item.get("station_code") or "") != wanted_station:
            continue
        if wanted_city and str(item.get("city_name") or "") != wanted_city:
            continue
        day_text = item.get("audit_day")
        if start_day or end_day:
            try:
                item_day = date.fromisoformat(str(day_text)) if day_text else None
            except ValueError:
                item_day = None
            if item_day is None:
                continue
            if start_day and item_day < start_day:
                continue
            if end_day and item_day > end_day:
                continue
        if decision and record.get("decision") != decision:
            continue
        if status and record.get("status") != status:
            continue
        items.append(item)
    total = len(items)
    return {
        "status": "success",
        "data": {"total": total, "items": items[offset:offset + limit]},
    }


@router.get("/conclusions/{review_id}")
async def get_data_audit_conclusion(
    review_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    record = load_review(review_id)
    if record is None or record.get("task_id") != REVIEW_TASK_ID:
        raise HTTPException(status_code=404, detail="conclusion_not_found")
    return {"status": "success", "data": _detail_item(record)}
