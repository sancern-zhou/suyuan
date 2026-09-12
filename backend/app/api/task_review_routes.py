"""Authenticated, task-independent human-review endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services.task_review import (
    HumanDecision,
    decide_review,
    list_reviews_payload,
    load_review,
)
from app.utils.path_config import get_data_registry, is_path_within, resolve_agent_path

router = APIRouter(prefix="/api/task-reviews", tags=["task-reviews"])


def get_record(review_id):
    try:
        record = load_review(review_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "review_not_found")
    return record


@router.get("")
def index(pending_only: bool = True, category: str | None = None,
          limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
          user: CurrentUser = Depends(require_current_user)):
    payload = list_reviews_payload(pending_only=pending_only, category=category, limit=limit, offset=offset)
    keys = ("review_id", "task_id", "task_name", "execution_id", "category", "title", "summary", "status", "updated_at", "version")
    return {"reviews": [{key: record[key] for key in keys if key in record} for record in payload["records"]],
            "total": payload["total"], "categories": payload["categories"]}


@router.get("/{review_id}")
def detail(review_id: str, user: CurrentUser = Depends(require_current_user)):
    return {"review": get_record(review_id)}


@router.post("/{review_id}/decision")
def decide(review_id: str, request: HumanDecision, user: CurrentUser = Depends(require_current_user)):
    get_record(review_id)
    try:
        return {"review": decide_review(review_id, request.model_dump(mode="json"),
                                        {"user_id": user.id, "username": user.username})}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{review_id}/evidence/{index}")
def evidence(review_id: str, index: int, user: CurrentUser = Depends(require_current_user)):
    record = get_record(review_id)
    if index < 0 or index >= len(record["evidence"]):
        raise HTTPException(404, "evidence_not_found")
    path = resolve_agent_path(record["evidence"][index]["path"])
    if not is_path_within(path, [get_data_registry()]) or not path.is_file():
        raise HTTPException(404, "evidence_not_found")
    return FileResponse(path, filename=path.name, headers={"X-Content-Type-Options": "nosniff"})
