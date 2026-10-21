import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import human_feedback_routes as routes
from app.auth.models import CurrentUser
from app.agent.session.models import Session
from app.agent.react_agent import _human_feedback_learning_mode, _is_human_feedback_resume
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource
from app.services.ops_audit.review_artifacts import issue_list_sha256


class _Catalog:
    async def require_write(self, session_id, user):
        return ConversationCatalogRecord(
            session_id=session_id,
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            source=ConversationSource.WEB,
            mode="ops",
        )


def test_generic_feedback_persists_review_context_and_returns_resume_query(monkeypatch):
    session = Session(session_id="session-feedback", query="审核工单", metadata={})
    saved = []

    async def load_session(session_id, *, mode=None, include_messages=True):
        assert session_id == session.session_id
        assert mode == "ops"
        assert include_messages is False
        return session

    async def save_metadata(value, *, mode=None):
        saved.append((value, mode))
        return True

    monkeypatch.setattr(routes, "load_session_for_mode", load_session)
    monkeypatch.setattr(routes, "save_session_metadata_for_mode", save_metadata)

    request = routes.HumanFeedbackRequest(
        scenario="generic",
        learning_mode="ops",
        feedback_id="feedback-generic-1",
        items=[
            routes.HumanFeedbackItem(
                item_id="issue-1",
                decision="include",
                comment="原始记录已核对",
            )
        ],
        comment="本次审核完成",
    )
    user = CurrentUser(
        id="operator-1",
        username="operator",
        display_name="运维人员",
    )

    result = asyncio.run(
        routes.submit_human_feedback(
            session.session_id,
            request,
            user=user,
            catalog=_Catalog(),
        )
    )

    assert result["success"] is True
    assert result["feedback_id"] == "feedback-generic-1"
    assert "issue-1" in result["resume_query"]
    assert "原始记录已核对" in result["resume_query"]
    assert session.conversation_history == []
    assert session.metadata["last_human_feedback"]["comment"] == "本次审核完成"
    assert session.metadata["last_human_feedback"]["learning_mode"] == "ops"
    assert len(session.metadata["human_feedback_history"]) == 1
    assert saved == [(session, "ops")]
    assert _is_human_feedback_resume(result["resume_query"]) is True
    assert _human_feedback_learning_mode(result["resume_query"], "assistant") == "ops"
    assert _is_human_feedback_resume("继续生成报告") is False


def test_feedback_learning_mode_falls_back_for_invalid_or_unstructured_queries():
    assert _human_feedback_learning_mode("继续生成报告", "assistant") == "assistant"
    assert _human_feedback_learning_mode(
        "【人工反馈续跑】用户反馈已提交。\n"
        "本次反馈明细（请据此总结经验）："
        f"{json.dumps({'learning_mode': 'unknown-mode'}, ensure_ascii=False)}",
        "assistant",
    ) == "assistant"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_legacy_ops_audit_report_is_migrated_into_registry_once(tmp_path, monkeypatch):
    backend_root = tmp_path / "project" / "backend"
    registry = tmp_path / "configured-registry"
    legacy_dir = backend_root / "backend_data_registry" / "memory" / "ops" / "audit"
    source_path = legacy_dir / "latest_finished_work_orders_final_issue_list.json"
    report_path = legacy_dir / routes.REPORT_INPUT_FILENAME
    source = {"schema_version": "test.v1", "items": [], "pending_semantic_reviews": []}
    source_sha256 = issue_list_sha256(source)
    report = {
        "schema_version": "ops_audit_report_input.v3",
        "source": {
            "sha256": source_sha256,
            "issue_count": 0,
            "path": str(source_path.resolve()),
        },
        "pending_review_items": [],
        "pending_semantic_reviews": [],
    }
    _write_json(source_path, source)
    _write_json(report_path, report)
    dataset_path = legacy_dir / "latest_finished_work_orders_dataset.json"
    _write_json(dataset_path, {"rows": [1]})
    legacy_report_text = report_path.read_text(encoding="utf-8")

    monkeypatch.setattr(routes, "BACKEND_ROOT", backend_root)
    monkeypatch.setattr(routes, "get_data_registry", lambda: registry)

    migrated_report_path = routes._data_path(str(report_path))
    expected_dir = registry / "memory" / "ops" / "audit" / "recovered" / source_sha256
    assert migrated_report_path == (expected_dir / routes.REPORT_INPUT_FILENAME).resolve()
    assert (expected_dir / dataset_path.name).is_file()
    assert json.loads(migrated_report_path.read_text(encoding="utf-8"))["source"]["path"] == str(
        (expected_dir / source_path.name).resolve()
    )
    assert report_path.read_text(encoding="utf-8") == legacy_report_text

    migrated_report_path.write_text("already updated", encoding="utf-8")
    assert routes._data_path(str(report_path)) == migrated_report_path
    assert migrated_report_path.read_text(encoding="utf-8") == "already updated"


def test_unregistered_nonlegacy_feedback_path_remains_forbidden(tmp_path, monkeypatch):
    registry = tmp_path / "configured-registry"
    unrelated_path = tmp_path / "elsewhere" / routes.REPORT_INPUT_FILENAME
    _write_json(unrelated_path, {})
    monkeypatch.setattr(routes, "BACKEND_ROOT", tmp_path / "project" / "backend")
    monkeypatch.setattr(routes, "get_data_registry", lambda: registry)

    with pytest.raises(HTTPException) as exc_info:
        routes._data_path(str(unrelated_path))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "feedback_path_outside_registry"
