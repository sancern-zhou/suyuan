from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.agent.active_contexts import (
    active_contexts_metadata,
    effective_active_context_items,
    resolve_active_contexts,
)
from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.resources.resource_service import StoredResource
from app.agent.session.session_manager_db import SessionManagerDB


def _policy_resource(path, resource_id="policy-1"):
    now = datetime.now(timezone.utc)
    return StoredResource(
        session_id="session-1",
        resource_key=f"file:{path}",
        resource_id=resource_id,
        kind="file",
        role="attachment",
        label=path.name,
        locator={"path": str(path)},
        presentation_type="document",
        presentation={"format": "md", "preview": {}},
        metadata={"source": "user_upload", "mime_type": "text/markdown"},
        tool_name="upload_chat_file",
        run_id="upload-1",
        turn_sequence=0,
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_active_context_replacement_and_legacy_skill_semantics():
    metadata = {
        "active_contexts": active_contexts_metadata([
            {"type": "skill", "id": "old-skill"},
            {"type": "fixed_policy", "id": "policy-1"},
        ])
    }

    assert effective_active_context_items(metadata, None, []) == [
        {"type": "skill", "id": "old-skill"},
        {"type": "fixed_policy", "id": "policy-1"},
    ]
    assert effective_active_context_items(metadata, [], []) == []
    assert effective_active_context_items(metadata, None, ["new-skill"]) == [
        {"type": "skill", "id": "new-skill"},
        {"type": "fixed_policy", "id": "policy-1"},
    ]


def test_fixed_policy_is_reloaded_from_authoritative_file(tmp_path):
    policy = tmp_path / "requirements.md"
    policy.write_text("必须逐条响应。", encoding="utf-8")
    resource = _policy_resource(policy)
    items = [{"type": "fixed_policy", "id": resource.resource_id}]

    first = resolve_active_contexts(items, mode="assistant", resources=[resource])
    assert "必须逐条响应。" in first.fixed_policy_context

    policy.write_text("必须逐条响应，并完成验收。", encoding="utf-8")
    second = resolve_active_contexts(items, mode="assistant", resources=[resource])
    assert "并完成验收" in second.fixed_policy_context


def test_fixed_policy_rejects_unsupported_binary_documents(tmp_path):
    policy = tmp_path / "requirements.docx"
    policy.write_bytes(b"not-a-real-docx")
    resource = _policy_resource(policy)

    with pytest.raises(ValueError, match="unsupported active policy format"):
        resolve_active_contexts(
            [{"type": "fixed_policy", "id": resource.resource_id}],
            mode="assistant",
            resources=[resource],
        )


def test_fixed_policy_context_is_injected_outside_compressible_history():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "assistant"
    builder.fixed_policy_context = "fixed-policy-marker"
    prompt = builder._build_system_prompt()
    assert prompt.count("fixed-policy-marker") == 1
    assert "<fixed_policies>" in prompt


def test_session_metadata_merge_keeps_the_newest_active_contexts():
    older = {
        "version": 1,
        "updated_at": "2026-07-29T01:00:00+00:00",
        "items": [{"type": "skill", "id": "older"}],
    }
    newer = {
        "version": 1,
        "updated_at": "2026-07-29T02:00:00+00:00",
        "items": [{"type": "skill", "id": "newer"}],
    }

    merged = SessionManagerDB._merge_preserved_metadata(
        {"active_contexts": newer},
        {"active_contexts": older},
    )
    assert merged["active_contexts"] == newer

    merged = SessionManagerDB._merge_preserved_metadata(
        {"active_contexts": older},
        {"active_contexts": newer},
    )
    assert merged["active_contexts"] == newer
