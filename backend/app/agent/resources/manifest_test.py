from app.agent.resources.manifest import (
    derive_legacy_views,
    merge_resource_refs,
    project_session_resources,
)
from app.agent.resources.models import (
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    ResourceStatus,
    SessionResourceRef,
)


def make_ref(data_id: str, *, run_id: str, logical_key: str | None = None) -> SessionResourceRef:
    return SessionResourceRef.create(
        kind=ResourceKind.DATA,
        locator=ResourceLocator(data_id=data_id),
        logical_key=logical_key,
        role=ResourceRole.PRIMARY,
        label=data_id,
        tool_name="query",
        run_id=run_id,
        turn_sequence=1,
    )


def test_empty_incoming_does_not_clear_or_mutate_existing_refs():
    existing = [make_ref("data:v1:a", run_id="run-a")]
    merged = merge_resource_refs(existing, [])
    assert merged == existing
    assert merged[0] is not existing[0]


def test_merge_is_idempotent_and_updates_provenance():
    first = make_ref("data:v1:a", run_id="run-a")
    later = make_ref("data:v1:a", run_id="run-b")
    merged = merge_resource_refs([first], [later])
    assert len(merged) == 1
    assert merged[0].run_id == "run-b"
    assert merged[0].created_at == first.created_at


def test_new_logical_slot_value_supersedes_old_value():
    old = make_ref("data:v1:a", run_id="run-a", logical_key="result.primary")
    new = make_ref("data:v1:b", run_id="run-b", logical_key="result.primary")
    merged = merge_resource_refs([old], [new])
    assert next(ref for ref in merged if ref.ref_id == old.ref_id).status is ResourceStatus.SUPERSEDED
    assert old.ref_id in next(ref for ref in merged if ref.ref_id == new.ref_id).supersedes


def test_projection_excludes_inactive_refs_and_honors_budget():
    refs = [make_ref(f"data:v1:{index}", run_id="run") for index in range(40)]
    refs[0].status = ResourceStatus.MISSING
    text = project_session_resources(
        refs,
        query="latest data",
        available_tools={"read_data_registry"},
        max_chars=1200,
    )
    assert "data:v1:0 |" not in text
    assert len(text) <= 1200
    assert "additional resources" in text


def test_legacy_views_use_only_active_refs():
    active = make_ref("data:v1:active", run_id="run")
    inactive = make_ref("data:v1:old", run_id="run")
    inactive.status = ResourceStatus.SUPERSEDED
    assert derive_legacy_views([active, inactive]).data_ids == ["data:v1:active"]
