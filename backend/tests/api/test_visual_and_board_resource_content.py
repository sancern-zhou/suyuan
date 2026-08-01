from datetime import UTC, datetime

import pytest

from app.agent.resources.resource_service import StoredResource
from app.api import session_resource_routes


def stored(path, *, kind, renderer, media_type, resource_id):
    now = datetime.now(UTC)
    return StoredResource(
        resource_id=resource_id,
        session_id="session-1",
        group_id="group-1",
        parent_resource_id=None,
        resource_key="primary",
        relation="primary",
        kind=kind,
        role="output",
        label=path.name,
        locator={"path": str(path)},
        format=path.suffix.lstrip("."),
        media_type=media_type,
        renderer=renderer,
        capabilities=["preview", "download"],
        metadata={},
        tool_name="test",
        run_id="run-1",
        turn_sequence=0,
        version=1,
        status="active",
        created_at=now,
        updated_at=now,
    )


class Catalog:
    async def require_read(self, *_args):
        return object()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "renderer", "media_type", "filename"),
    [
        ("visual", "chart", "application/json", "chart.json"),
        ("artifact", "board", "application/xml", "board.drawio"),
    ],
)
async def test_visual_and_board_use_the_same_opaque_content_route(
    tmp_path, monkeypatch, kind, renderer, media_type, filename
):
    registry = tmp_path / "registry"
    registry.mkdir()
    path = registry / filename
    path.write_text("{}" if filename.endswith("json") else "<mxfile/>")
    resource = stored(
        path,
        kind=kind,
        renderer=renderer,
        media_type=media_type,
        resource_id=f"resource-{renderer}",
    )

    class Service:
        async def get_resource(self, *_args, **_kwargs):
            return resource

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    response = await session_resource_routes.get_session_resource_content(
        "session-1",
        resource.resource_id,
        user=object(),
        catalog=Catalog(),
    )

    assert response.media_type == media_type
    assert response.headers["content-disposition"].startswith("inline;")
