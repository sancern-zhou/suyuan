from app.agent.resources.models import (
    ResourceImportance,
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    ResourceStatus,
    SessionResourceRef,
)


def _data_ref(data_id: str = "dataset:v1:a") -> SessionResourceRef:
    return SessionResourceRef.create(
        kind=ResourceKind.DATA,
        locator=ResourceLocator(data_id=data_id),
        role=ResourceRole.PRIMARY,
        label="Dataset",
        tool_name="query",
        run_id="run-a",
        turn_sequence=1,
    )


def test_ref_id_is_stable_for_equivalent_file_paths(tmp_path):
    target = tmp_path / "out" / "report.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")
    first = SessionResourceRef.create(
        kind=ResourceKind.FILE,
        locator=ResourceLocator(path=str(target)),
        role=ResourceRole.OUTPUT,
        label="Report",
        tool_name="report_tool",
        run_id="run-a",
        turn_sequence=1,
    )
    second = SessionResourceRef.create(
        kind=ResourceKind.FILE,
        locator=ResourceLocator(path=str(target.parent / "." / target.name)),
        role=ResourceRole.OUTPUT,
        label="Report v2",
        tool_name="report_tool",
        run_id="run-b",
        turn_sequence=2,
    )
    assert first.ref_id == second.ref_id
    assert first.locator.path == str(target.resolve())


def test_locator_requires_exactly_one_primary_identifier():
    try:
        ResourceLocator(data_id="dataset:v1:a", path="/tmp/a.json")
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("mixed locator must fail")


def test_new_reference_defaults_to_active_and_normal():
    ref = _data_ref()
    assert ref.status is ResourceStatus.ACTIVE
    assert ref.importance is ResourceImportance.NORMAL
