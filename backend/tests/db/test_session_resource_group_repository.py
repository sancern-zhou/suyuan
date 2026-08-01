from inspect import getsource
from types import SimpleNamespace

from app.agent.resources.resource_service import StoredResource
from app.db.session_resources_repository import SessionResourcesRepository, _stored


def test_repository_projects_every_group_delivery_field():
    row = SimpleNamespace(
        resource_id="resource-1",
        session_id="session-1",
        group_id="group-1",
        parent_resource_id="parent-1",
        resource_key="preview",
        relation="preview",
        kind="file",
        role="output",
        label="Preview",
        locator={"path": "/tmp/preview.pdf"},
        format="pdf",
        media_type="application/pdf",
        renderer="pdf",
        capabilities=["preview", "download"],
        resource_metadata={"page_count": 2},
        tool_name="render",
        run_id="run-1",
        turn_sequence=3,
        version=4,
        status="active",
        created_at=None,
        updated_at=None,
    )

    stored = _stored(row)

    assert isinstance(stored, StoredResource)
    assert stored.group_id == "group-1"
    assert stored.parent_resource_id == "parent-1"
    assert stored.renderer == "pdf"
    assert stored.version == 4


def test_repository_publication_methods_are_transactional_and_lock_versions():
    assert hasattr(SessionResourcesRepository, "publish_group")
    assert hasattr(SessionResourcesRepository, "attach_resources")
    source = getsource(SessionResourcesRepository)
    assert "async with db.begin()" in source
    assert ".with_for_update()" in source
