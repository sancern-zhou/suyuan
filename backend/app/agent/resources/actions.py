"""Trusted action-link projection for session resources."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from app.tools.resource_declarations import derivative_file

from .contracts import ResourceDeclaration
from .resource_service import StoredResource


def resource_content_base(session_id: str, resource: StoredResource) -> str:
    session = quote(session_id, safe="")
    resource_id = quote(resource.resource_id, safe="")
    return f"/api/sessions/{session}/resources/{resource_id}/content"


def resource_action_links(
    session_id: str, resource: StoredResource
) -> dict[str, str]:
    """Derive links only from trusted resource identity and capabilities."""
    base = resource_content_base(session_id, resource)
    directory = resource.kind == "artifact" and bool(
        resource.metadata.get("entrypoint")
    )
    actions: dict[str, str] = {}
    if "preview" in resource.capabilities:
        actions["preview"] = f"{base}/" if directory else base
    if "download" in resource.capabilities and not directory:
        actions["download"] = f"{base}?disposition=attachment"
    if "render" in resource.capabilities:
        actions["render"] = base.removesuffix("/content") + "/render"
    return actions


async def attach_rendered_file(
    service,
    *,
    session_id: str,
    run_id: str,
    group_key: str,
    parent_resource_id: str,
    path: str | Path,
    relation: str,
    renderer: str,
    tool_name: str,
    capabilities: tuple[str, ...] = ("preview", "download"),
    label: str | None = None,
) -> dict:
    """Attach a render result and return the sole mutation receipt contract."""
    parent = await service.get_resource(session_id, parent_resource_id)
    if parent is None:
        raise ValueError("active parent resource was not found")
    payload = derivative_file(
        path,
        group_key=group_key,
        parent_key=parent.resource_key,
        tool_name=tool_name,
        relation=relation,
        role=parent.role,
        renderer=renderer,
        capabilities=capabilities,
        label=label,
    )
    publication = await service.attach_resources(
        session_id,
        run_id,
        parent_resource_id,
        [ResourceDeclaration.model_validate(payload)],
    )
    return {
        "success": True,
        "resource_version": publication.catalog_version,
        "changed_resource_ids": [
            resource.resource_id for resource in publication.resources
        ],
    }
