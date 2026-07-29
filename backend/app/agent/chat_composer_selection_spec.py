from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.resources.models import (
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    ResourceStatus,
    SessionResourceRef,
)
from app.agent.resources.resource_service import StoredResource
from app.agent.selection_context import (
    InvalidContextReference,
    build_uploaded_file_ref,
    describe_skill_item,
    load_skill_selection,
    mark_uploaded_file_missing,
    resource_refs_to_message_attachments,
    resource_refs_to_runtime_attachments,
    select_conversation_files,
    selected_resource_projection,
    serialize_conversation_files,
)
from app.routers.agent import AgentAnalyzeRequest


def _ref(ref_id: str, *, kind=ResourceKind.FILE, status=ResourceStatus.ACTIVE):
    now = datetime.now(UTC)
    return SessionResourceRef(
        ref_id=ref_id,
        kind=kind,
        locator=ResourceLocator(path=f"/tmp/{ref_id}.txt"),
        role=ResourceRole.ATTACHMENT,
        label=f"{ref_id}.txt",
        tool_name="upload_chat_file",
        run_id="upload",
        turn_sequence=0,
        status=status,
        created_at=now,
        last_seen_at=now,
    )


def _stored_resource(
    tmp_path,
    *,
    resource_id: str = "resource-1",
    file_id: str = "file-1",
    filename: str = "upload.png",
    mime_type: str = "image/png",
    status: str = "active",
    create_file: bool = True,
) -> StoredResource:
    path = tmp_path / filename
    if create_file:
        path.write_bytes(b"data")
    now = datetime.now(UTC)
    return StoredResource(
        session_id="session-1",
        resource_key=f"upload:{file_id}",
        resource_id=resource_id,
        kind="file",
        role="source",
        label=filename,
        locator={"path": str(path)},
        presentation_type=None,
        presentation=None,
        metadata={"file_id": file_id, "mime_type": mime_type},
        tool_name="upload_chat",
        run_id=f"upload:{file_id}",
        turn_sequence=0,
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_analyze_request_requires_structured_selection_arrays():
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="分析数据")


def test_analyze_request_rejects_legacy_attachments():
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="分析数据", skill_ids=[], context_refs=[], attachments=[{"file_id": "legacy"}])


def test_analyze_request_accepts_empty_query_with_a_selection():
    request = AgentAnalyzeRequest(
        query="",
        skill_ids=["trend_analysis"],
        context_refs=[{
            "type": "conversation_file",
            "resource_id": "resource-1",
            "display_name": "数据.xlsx",
        }],
    )
    assert request.skill_ids == ["trend_analysis"]
    assert request.context_refs[0].resource_id == "resource-1"


def test_analyze_request_rejects_empty_turn_and_multiple_skills():
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="", skill_ids=[], context_refs=[])
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="分析", skill_ids=["trend", "report"], context_refs=[])


@pytest.mark.parametrize("mode", ["assistant", "ppt", "expert", "query", "report", "chart", "board", "ops"])
def test_selected_skill_context_is_injected_once_for_every_mode(mode):
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = mode
    builder.selected_skill_context = "selected-skill-marker"
    prompt = builder._build_system_prompt()
    assert prompt.count("selected-skill-marker") == 1
    assert "<selected_skill>" in prompt


def test_fixed_policy_context_is_injected_outside_compressible_history():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "assistant"
    builder.fixed_policy_context = "fixed-policy-marker"
    prompt = builder._build_system_prompt()
    assert prompt.count("fixed-policy-marker") == 1
    assert "<fixed_policies>" in prompt


def test_select_conversation_files_validates_type_status_and_order():
    refs = [
        _ref("one"),
        _ref("artifact", kind=ResourceKind.ARTIFACT),
        _ref("data", kind=ResourceKind.DATA),
        _ref("inactive", status=ResourceStatus.MISSING),
    ]
    assert [ref.ref_id for ref in select_conversation_files(refs, ["artifact", "one"])] == ["artifact", "one"]
    for invalid in ("data", "inactive", "missing"):
        with pytest.raises(InvalidContextReference):
            select_conversation_files(refs, [invalid])


def test_prompt_resource_projection_keeps_saved_refs_without_explicit_selection():
    saved_refs = [_ref("saved")]

    assert selected_resource_projection(None, saved_refs=saved_refs) == saved_refs
    assert selected_resource_projection([], saved_refs=saved_refs) == saved_refs


def test_current_turn_image_ref_must_resolve_to_an_existing_file(tmp_path):
    missing = _stored_resource(
        tmp_path,
        resource_id="missing-image-resource",
        file_id="missing-image",
        filename="missing.png",
        create_file=False,
    )

    with pytest.raises(ValueError, match="current_turn_image_missing"):
        resource_refs_to_runtime_attachments([missing])


def test_skill_loading_and_mode_compatibility(tmp_path):
    skill = tmp_path / "trend.md"
    skill.write_text(
        "# 趋势分析\n\n## 概述\n比较数据趋势。\n\n## 所需工具\n- `read_file`\n- `generate_chart`\n",
        encoding="utf-8",
    )
    (tmp_path / "skills_metadata.json").write_text(
        '{"skills":{"trend":{"enabled":true,"aliases":["趋势"],'
        '"required_tools":["read_file","generate_chart"]}}}',
        encoding="utf-8",
    )
    selection = load_skill_selection("trend", skills_dir=tmp_path, available_tools={"read_file", "generate_chart"})
    assert selection.required_tools == ["read_file", "generate_chart"]
    assert "比较数据趋势" in selection.content
    descriptor = describe_skill_item(
        {"name": "趋势分析", "file": str(skill), "description": "比较趋势"},
        available_tools={"read_file"},
    )
    assert descriptor["id"] == "trend"
    assert descriptor["compatible"] is False
    assert descriptor["missing_tools"] == ["generate_chart"]
    assert descriptor["aliases"] == ["趋势"]
    with pytest.raises(ValueError, match="missing required tools"):
        load_skill_selection("trend", skills_dir=tmp_path, available_tools={"read_file"})


def test_disabled_skill_metadata_prevents_template_selection(tmp_path):
    (tmp_path / "template.md").write_text("# 模板", encoding="utf-8")
    (tmp_path / "skills_metadata.json").write_text(
        '{"skills":{"template":{"enabled":false,"required_tools":[]}}}',
        encoding="utf-8",
    )

    descriptor = describe_skill_item({"name": "模板", "file": str(tmp_path / "template.md")})
    assert descriptor["enabled"] is False
    with pytest.raises(ValueError, match="disabled"):
        load_skill_selection("template", skills_dir=tmp_path)


def test_published_tool_dependent_skill_is_rejected_in_incompatible_mode():
    with pytest.raises(ValueError, match="ops_audit_fetch_dataset"):
        load_skill_selection(
            "fault_work_order_analysis",
            available_tools={"read_file"},
        )


def test_uploaded_files_are_safe_to_list_and_images_support_native_input(tmp_path):
    spreadsheet = tmp_path / "upload.xlsx"
    spreadsheet.write_bytes(b"data")
    file_ref = build_uploaded_file_ref(
        file_id="file-1",
        file_path=str(spreadsheet),
        filename="数据.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    payload = serialize_conversation_files([file_ref])[0]
    assert payload["metadata"]["source"] == "user_upload"
    assert payload["metadata"]["file_id"] == "file-1"
    assert "locator" not in payload

    non_image = _stored_resource(
        tmp_path,
        file_id="file-1",
        filename="upload.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert resource_refs_to_runtime_attachments([non_image]) == []


def test_persisted_uploaded_image_supports_native_input(tmp_path):
    image_ref = _stored_resource(
        tmp_path, file_id="image-1", filename="persisted-image.png"
    )

    assert resource_refs_to_runtime_attachments([image_ref])[0]["local_path"] == str(
        (tmp_path / "persisted-image.png").resolve()
    )


def test_inactive_persisted_image_is_rejected(tmp_path):
    image_ref = _stored_resource(tmp_path, status="missing")

    with pytest.raises(ValueError, match="current_turn_image_invalid: resource-1"):
        resource_refs_to_runtime_attachments([image_ref])


def test_uploaded_image_ref_builds_safe_message_attachment(tmp_path):
    image_ref = _stored_resource(
        tmp_path, file_id="image-1", filename="现场.png"
    )

    assert resource_refs_to_message_attachments([image_ref]) == [{
        "file_id": "image-1",
        "name": "现场.png",
        "type": "image",
        "mime_type": "image/png",
        "url": "/api/upload/image-1",
    }]


def test_deleted_upload_is_marked_missing(tmp_path):
    path = tmp_path / "upload.txt"
    path.write_text("data", encoding="utf-8")
    ref = build_uploaded_file_ref(
        file_id="file-1", file_path=str(path), filename="数据.txt", mime_type="text/plain"
    )
    changed = mark_uploaded_file_missing([ref], "file-1")
    assert len(changed) == 1
    assert changed[0].status is ResourceStatus.MISSING
