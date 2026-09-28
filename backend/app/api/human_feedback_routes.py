"""Reusable human-feedback handoff for Agent workflows."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.session.session_resolver import (
    load_session_for_mode,
    save_session_metadata_for_mode,
)
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.services.ops_audit.review_artifacts import (
    REPORT_INPUT_FILENAME,
    apply_human_feedback,
    issue_list_sha256,
)
from app.utils.path_config import BACKEND_ROOT, get_data_registry, resolve_agent_path

router = APIRouter(prefix="/api/agent", tags=["agent-feedback"])
logger = structlog.get_logger()

_OPS_AUDIT_FINAL_ISSUES_FILENAME = "latest_finished_work_orders_final_issue_list.json"
_LEGACY_OPS_AUDIT_ARTIFACT_PATTERN = "latest_finished_work_orders_*.json"
_LEGACY_MIGRATION_MANIFEST = ".legacy_migration.json"


class HumanFeedbackItem(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=512)
    decision: Literal["include", "exclude", "pending"]
    comment: str = Field(default="", max_length=4000)


class HumanFeedbackRequest(BaseModel):
    scenario: str = Field(default="generic", min_length=1, max_length=120)
    learning_mode: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    feedback_id: str | None = Field(default=None, max_length=200)
    report_input_path: str | None = Field(default=None, min_length=1, max_length=2000)
    source_sha256: str | None = Field(default=None, min_length=1, max_length=128)
    items: list[HumanFeedbackItem] = Field(..., min_length=1, max_length=1000)
    comment: str = Field(default="", max_length=4000)


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path.name}")
    return value


def _copy_regular_tree(source: Path, target: Path) -> None:
    """Copy evidence files without following links outside the legacy run."""

    if not source.is_dir() or source.is_symlink():
        return
    for child in source.rglob("*"):
        if child.is_symlink():
            continue
        relative = child.relative_to(source)
        destination = target / relative
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif child.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, destination)


def _existing_legacy_migration(target_dir: Path, source_sha256: str) -> Path | None:
    report_path = target_dir / REPORT_INPUT_FILENAME
    manifest_path = target_dir / _LEGACY_MIGRATION_MANIFEST
    if not report_path.is_file() or not manifest_path.is_file():
        return None
    manifest = _read_json_object(manifest_path)
    if manifest.get("source_sha256") != source_sha256:
        raise ValueError("legacy audit migration identity does not match")
    return report_path.resolve()


def _migrate_legacy_ops_audit_report(path: Path) -> Path | None:
    """Move the one historical fixed audit location behind the registry boundary."""

    legacy_dir = (BACKEND_ROOT / "backend_data_registry" / "memory" / "ops" / "audit").resolve()
    legacy_report_path = legacy_dir / REPORT_INPUT_FILENAME
    if path != legacy_report_path:
        return None

    report = _read_json_object(legacy_report_path)
    source_meta = report.get("source") if isinstance(report.get("source"), dict) else {}
    source_sha256 = str(source_meta.get("sha256") or "").strip().lower()
    if len(source_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_sha256):
        raise ValueError("legacy audit report has no valid source hash")

    legacy_source_path = (legacy_dir / _OPS_AUDIT_FINAL_ISSUES_FILENAME).resolve()
    declared_source_path = Path(str(source_meta.get("path") or "")).expanduser().resolve()
    if declared_source_path != legacy_source_path or not legacy_source_path.is_file():
        raise ValueError("legacy audit report source is unavailable")
    source = _read_json_object(legacy_source_path)
    if issue_list_sha256(source) != source_sha256:
        raise ValueError("legacy audit source changed after the feedback panel was opened")

    target_dir = (
        get_data_registry().resolve()
        / "memory"
        / "ops"
        / "audit"
        / "recovered"
        / source_sha256
    )
    existing = _existing_legacy_migration(target_dir, source_sha256)
    if existing is not None:
        return existing

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = target_dir.parent / f".{source_sha256}.{uuid4().hex}.tmp"
    temporary_dir.mkdir()
    try:
        for artifact in legacy_dir.glob(_LEGACY_OPS_AUDIT_ARTIFACT_PATTERN):
            if artifact.is_file() and not artifact.is_symlink():
                shutil.copy2(artifact, temporary_dir / artifact.name)
        _copy_regular_tree(legacy_dir / "visual_evidence", temporary_dir / "visual_evidence")

        migrated_source_path = temporary_dir / _OPS_AUDIT_FINAL_ISSUES_FILENAME
        migrated_report_path = temporary_dir / REPORT_INPUT_FILENAME
        if not migrated_source_path.is_file() or not migrated_report_path.is_file():
            raise ValueError("legacy audit artifacts are incomplete")
        migrated_report = _read_json_object(migrated_report_path)
        migrated_report["source"]["path"] = str(
            (target_dir / _OPS_AUDIT_FINAL_ISSUES_FILENAME).resolve()
        )
        migrated_report_path.write_text(
            json.dumps(migrated_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temporary_dir / _LEGACY_MIGRATION_MANIFEST).write_text(
            json.dumps(
                {
                    "schema_version": "ops_audit_legacy_migration.v1",
                    "source_sha256": source_sha256,
                    "legacy_report_input_path": str(legacy_report_path),
                    "legacy_source_path": str(legacy_source_path),
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            os.rename(temporary_dir, target_dir)
        except OSError:
            existing = _existing_legacy_migration(target_dir, source_sha256)
            if existing is None:
                raise
            return existing
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)

    logger.info(
        "legacy_ops_audit_artifacts_migrated",
        source=str(legacy_report_path),
        target=str(target_dir),
        source_sha256=source_sha256,
    )
    return (target_dir / REPORT_INPUT_FILENAME).resolve()


def _data_path(value: str) -> Path:
    try:
        path = resolve_agent_path(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_feedback_path") from exc
    try:
        path.relative_to(get_data_registry().resolve())
    except ValueError as exc:
        try:
            migrated_path = _migrate_legacy_ops_audit_report(path)
        except (OSError, ValueError, json.JSONDecodeError) as migration_exc:
            logger.warning(
                "legacy_ops_audit_artifact_migration_failed",
                path=str(path),
                error=str(migration_exc),
            )
            raise HTTPException(status_code=409, detail="legacy_feedback_artifact_invalid") from migration_exc
        if migrated_path is None:
            raise HTTPException(status_code=403, detail="feedback_path_outside_registry") from exc
        return migrated_path
    return path


@router.post("/{session_id}/human-feedback")
async def submit_human_feedback(
    session_id: str,
    request: HumanFeedbackRequest,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Apply user decisions, persist the raw feedback in the session, and return a resume prompt.

    Memory and case-library maintenance remains an Agent responsibility. This
    endpoint only records the user's source feedback and updates deterministic
    report artifacts.
    """

    catalog_record = await catalog.require_write(session_id, user)
    report_path = _data_path(request.report_input_path) if request.report_input_path else None
    if report_path is not None and not report_path.is_file():
        raise HTTPException(status_code=404, detail="report_input_not_found")

    session_mode = catalog_record.mode
    session = await load_session_for_mode(
        session_id,
        mode=session_mode,
        include_messages=False,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    learning_mode = request.learning_mode or session_mode

    feedback_id = request.feedback_id or f"feedback_{uuid4().hex}"
    reviewer = {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }
    updated: dict[str, Any] = {"report_ready": True, "summary": {}}
    if report_path is not None:
        if not request.source_sha256:
            raise HTTPException(status_code=422, detail="source_sha256_required")
        try:
            updated = apply_human_feedback(
                report_path,
                [item.model_dump() for item in request.items],
                expected_source_sha256=request.source_sha256,
                feedback_id=feedback_id,
                reviewer=reviewer,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail="invalid_report_input") from exc

    feedback_record = {
        "feedback_id": feedback_id,
        "scenario": request.scenario,
        "learning_mode": learning_mode,
        "reviewer": reviewer,
        "items": [item.model_dump() for item in request.items],
        "comment": request.comment.strip(),
        "report_input_path": str(report_path) if report_path else None,
        "report_ready": bool(updated.get("report_ready")),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    history = session.metadata.get("human_feedback_history", [])
    if not isinstance(history, list):
        history = []
    session.metadata["last_human_feedback"] = feedback_record
    session.metadata["human_feedback_history"] = [*history[-19:], feedback_record]
    if not await save_session_metadata_for_mode(session, mode=session_mode):
        raise HTTPException(status_code=500, detail="human_feedback_session_save_failed")

    feedback_context = json.dumps(
        {
            "feedback_id": feedback_id,
            "scenario": request.scenario,
            "learning_mode": learning_mode,
            "items": feedback_record["items"],
            "comment": feedback_record["comment"],
        },
        ensure_ascii=False,
    )
    resume_query = (
        "【人工反馈续跑】用户反馈已提交。"
        + (
            f"请使用 report_input_path={report_path} 生成正式运维报告，"
            "严格以 report_ready 和 items 为准。"
            if report_path
            else "请结合本次反馈继续完成当前任务。"
        )
        + "完成任务时主动根据用户判定和审核意见总结可复用经验；任务结束后由记忆整合 Agent 自主决定"
        "是否写入对应学习域的长期记忆和案例库。不要再次要求用户确认已经提交的条目。\n"
        "本次反馈明细（请据此总结经验）："
        + feedback_context
    )
    return {
        "success": True,
        "feedback_id": feedback_id,
        "scenario": request.scenario,
        "learning_mode": learning_mode,
        "report_ready": bool(updated.get("report_ready")),
        "report_input_path": str(report_path) if report_path else None,
        "summary": updated.get("summary", {}),
        "resume_query": resume_query,
    }
