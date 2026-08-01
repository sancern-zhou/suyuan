"""Trusted action-link projection for session resources."""
from __future__ import annotations

from urllib.parse import quote

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
    return actions
