"""故障工单审核工作台 API：证据包读取 + 人工操作（反馈/归档/退回）。

证据数据按来源拆分存储（见 services/jiangsu_work_order_review），
前端工单审核 tab 从这里读取索引与分文件，避免一次性拉取大 JSON。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services import task_review
from app.services.jiangsu_work_order_review import (
    get_order,
    get_order_source,
    list_orders,
    record_operation,
)
from app.utils.path_config import get_data_registry, is_path_within, resolve_agent_path

router = APIRouter(prefix="/api/jiangsu/work-order-reviews", tags=["jiangsu-work-order-reviews"])


def _order_or_404(code: str) -> dict:
    try:
        return get_order(code)
    except KeyError:
        raise HTTPException(404, "work_order_review_not_found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
def index(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          status: str | None = None, keyword: str | None = None,
          user: CurrentUser = Depends(require_current_user)):
    return list_orders(limit=limit, offset=offset, status=status, keyword=keyword)


@router.get("/{code}")
def detail(code: str, user: CurrentUser = Depends(require_current_user)):
    return _order_or_404(code)


@router.get("/{code}/sources/{name}")
def source(code: str, name: str, user: CurrentUser = Depends(require_current_user)):
    try:
        return get_order_source(code, name)
    except KeyError:
        raise HTTPException(404, "source_not_found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{code}/attachments/{index}")
def attachment(code: str, index: int, user: CurrentUser = Depends(require_current_user)):
    """按序号返回工单附件文件（源平台原图），前端以 blob 方式渲染图片。"""
    try:
        payload = get_order_source(code, "work_order")
    except KeyError:
        raise HTTPException(404, "work_order_review_not_found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    attachments = (payload.get("data") or {}).get("attachments") or []
    if index < 0 or index >= len(attachments):
        raise HTTPException(404, "attachment_not_found")
    item = attachments[index]
    if not isinstance(item, dict) or item.get("download_status") != "success":
        raise HTTPException(404, "attachment_not_available")
    path = resolve_agent_path(item.get("local_path"))
    if not is_path_within(path, [get_data_registry()]) or not path.is_file():
        raise HTTPException(404, "attachment_not_found")
    return FileResponse(
        path,
        media_type=str(item.get("content_type") or "application/octet-stream"),
        filename=str(item.get("fileName") or path.name),
        headers={"X-Content-Type-Options": "nosniff"},
    )


class WorkOrderReviewOperationRequest(BaseModel):
    action: Literal["feedback", "archive", "reject"]
    comment: str = Field(default="", max_length=4000)
    intervals_confirmed: bool = False


def _decision_via_task_review(code: str, payload: WorkOrderReviewOperationRequest,
                              user: CurrentUser) -> bool:
    """存在 AI 审核记录时走 task_reviews 决策流（版本校验 + 退回复审钩子）。

    返回 True 表示已由 task_reviews 处理；False 表示无审核记录，退回简单状态流转。
    """
    payload_doc = _order_or_404(code)
    review_id = (payload_doc.get("entry") or {}).get("review_id")
    if not review_id:
        return False
    record = task_review.load_review(review_id)
    if record is None:
        return False
    action = "confirm" if payload.action == "archive" else "reject"
    allowed = {"pending_review": {"confirm", "reject", "start_disposal"},
               "in_disposal": {"complete", "reject"}}
    if action not in allowed.get(record.get("status"), set()):
        raise HTTPException(409, f"当前审核状态 {record.get('status')} 不允许 {payload.action}")
    decision = {
        "version": record["version"],
        "action": action,
        "decision": "approve" if action == "confirm" else "reject",
        "comment": payload.comment or ("人工归档确认" if action == "confirm" else "人工退回"),
        "data_impact": record.get("data_impact") or [],
        "intervals_confirmed": payload.intervals_confirmed,
    }
    try:
        task_review.decide_review(review_id, decision,
                                  {"user_id": user.id, "username": user.username})
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return True


@router.post("/{code}/operations")
def operations(code: str, payload: WorkOrderReviewOperationRequest,
               user: CurrentUser = Depends(require_current_user)):
    _order_or_404(code)
    actor = {"user_id": user.id, "username": user.username}
    if payload.action in {"archive", "reject"} and _decision_via_task_review(code, payload, user):
        # decide_review 的同步钩子已回写证据包状态与操作记录。
        return {"order": get_order(code)["entry"], "ok": True}
    try:
        record_operation(code, payload.action, payload.comment, actor)
    except KeyError:
        raise HTTPException(404, "work_order_review_not_found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"order": get_order(code)["entry"], "ok": True}
