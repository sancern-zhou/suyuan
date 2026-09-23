"""Dependency-scoped resource handoff for isolated workflow child sessions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import structlog

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import StoredResource
from app.tools.resource_declarations import primary_file
from app.utils.path_config import (
    get_data_registry,
    is_path_within,
    resolve_agent_path,
)

logger = structlog.get_logger(__name__)


def stored_resource_ref(resource: StoredResource) -> dict[str, Any]:
    """Return the typed, portable description used between workflow nodes."""
    ref = {
        "handle_type": "session_resource",
        "source_session_id": resource.session_id,
        "resource_id": resource.resource_id,
        "group_id": resource.group_id,
        "parent_resource_id": resource.parent_resource_id,
        "resource_key": resource.resource_key,
        "relation": resource.relation,
        "kind": resource.kind,
        "role": resource.role,
        "label": resource.label,
        "format": resource.format,
        "media_type": resource.media_type,
        "renderer": resource.renderer,
        "capabilities": list(resource.capabilities),
        "version": resource.version,
        "locator": dict(resource.locator or {}),
    }
    path = str((resource.locator or {}).get("path") or "").strip()
    if path:
        ref["file_path"] = path
    return ref


def _handoff_group_key(*parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()[:32]
    return f"workflow-input:{digest}"


def _metadata_with_origin(
    metadata: Mapping[str, Any] | None,
    origin: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve useful metadata without exceeding the declaration limit."""
    merged = dict(metadata or {})
    merged["workflow_origin"] = dict(origin)
    if len(json.dumps(merged, ensure_ascii=False, default=str).encode("utf-8")) <= 8192:
        return merged
    return {"workflow_origin": dict(origin)}


def _declaration_from_stored(
    resource: StoredResource,
    *,
    group_key: str,
    origin: Mapping[str, Any],
    parent_key: str | None = None,
) -> ResourceDeclaration:
    return ResourceDeclaration.model_validate({
        "kind": resource.kind,
        "group_key": group_key,
        "resource_key": resource.resource_key,
        "parent_key": parent_key,
        "relation": resource.relation,
        "role": "source",
        "label": resource.label,
        "locator": dict(resource.locator or {}),
        "format": resource.format,
        "media_type": resource.media_type,
        "renderer": resource.renderer,
        "capabilities": list(resource.capabilities),
        "metadata": _metadata_with_origin(resource.metadata, origin),
        "tool_name": "run_agent_workflow",
    })


def _declaration_from_file_handle(
    handle: Mapping[str, Any],
    *,
    group_key: str,
) -> ResourceDeclaration | None:
    raw_path = handle.get("file_path") or handle.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    try:
        path = resolve_agent_path(raw_path)
    except (OSError, ValueError):
        return None
    if not path.is_file() or not is_path_within(path, [get_data_registry()]):
        return None
    declaration = primary_file(
        path,
        group_key=group_key,
        tool_name="run_agent_workflow",
        role="source",
        label=str(handle.get("label") or handle.get("name") or path.name),
        metadata={
            "workflow_origin": {
                "source_task_id": str(handle.get("source_task_id") or ""),
                "handle_type": "file_path",
            }
        },
    )
    if handle.get("kind") == "data" or path.suffix.lower() in {".json", ".csv"}:
        declaration["kind"] = "data"
    return ResourceDeclaration.model_validate(declaration)


async def import_workflow_handles(
    service: Any,
    *,
    target_session_id: str,
    run_id: str,
    handles: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Register dependency resources in the downstream session catalog."""
    imported: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    source_groups: dict[tuple[str, str], list[StoredResource]] = {}
    source_group_tasks: dict[tuple[str, str], str] = {}
    file_handles: list[Mapping[str, Any]] = []

    for handle in handles:
        if not isinstance(handle, Mapping):
            continue
        source_session_id = str(handle.get("source_session_id") or "").strip()
        resource_id = str(handle.get("resource_id") or "").strip()
        file_path = str(handle.get("file_path") or handle.get("path") or "").strip()
        identity = (source_session_id, resource_id or file_path)
        if not identity[1] or identity in seen:
            continue
        seen.add(identity)
        if source_session_id and resource_id:
            source = await service.get_resource(source_session_id, resource_id, status="active")
            if source is not None:
                group_identity = (source_session_id, source.group_id)
                if group_identity not in source_groups:
                    page = await service.list_resources(
                        source_session_id,
                        group_id=source.group_id,
                        status="active",
                        limit=500,
                    )
                    source_groups[group_identity] = list(page.resources)
                source_group_tasks.setdefault(
                    group_identity,
                    str(handle.get("source_task_id") or ""),
                )
                continue
        file_handles.append(handle)

    for (source_session_id, source_group_id), resources in source_groups.items():
        if not resources:
            continue
        missing_paths = [
            resource
            for resource in resources
            if (resource.locator or {}).get("path")
            and not Path(str(resource.locator["path"])).exists()
        ]
        if missing_paths:
            logger.warning(
                "workflow_resource_group_source_missing",
                source_session_id=source_session_id,
                source_group_id=source_group_id,
                resource_ids=[resource.resource_id for resource in missing_paths],
            )
            continue
        group_key = _handoff_group_key(
            target_session_id,
            source_session_id,
            source_group_id,
        )
        key_by_id = {
            resource.resource_id: resource.resource_key for resource in resources
        }
        declarations = [
            _declaration_from_stored(
                resource,
                group_key=group_key,
                parent_key=key_by_id.get(resource.parent_resource_id or ""),
                origin={
                    "source_session_id": source_session_id,
                    "resource_id": resource.resource_id,
                    "source_group_id": source_group_id,
                    "source_task_id": source_group_tasks.get(
                        (source_session_id, source_group_id), ""
                    ),
                },
            )
            for resource in resources
        ]
        publication = await service.publish_group(
            target_session_id,
            run_id,
            group_key,
            declarations,
        )
        imported.extend(stored_resource_ref(item) for item in publication.resources)

    for handle in file_handles:
        file_path = str(handle.get("file_path") or handle.get("path") or "").strip()
        group_key = _handoff_group_key(target_session_id, "file_path", file_path)
        declaration = _declaration_from_file_handle(handle, group_key=group_key)
        if declaration is None:
            continue
        publication = await service.publish_group(
            target_session_id,
            run_id,
            group_key,
            [declaration],
        )
        imported.extend(stored_resource_ref(item) for item in publication.resources)
    return imported


def result_resource_declarations(
    workflow_id: str,
    node_results: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Expose child outputs to the parent session through the normal tool contract."""
    grouped_refs: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for task_id, result in (node_results or {}).items():
        data = result.get("data") if isinstance(result, Mapping) else None
        refs = data.get("resource_refs") if isinstance(data, Mapping) else None
        for ref in refs or []:
            if not isinstance(ref, Mapping):
                continue
            locator = ref.get("locator") if isinstance(ref.get("locator"), Mapping) else {}
            resource_id = str(ref.get("resource_id") or "").strip()
            source_session_id = str(ref.get("source_session_id") or "").strip()
            identity = (source_session_id, resource_id)
            if not resource_id or not locator or identity in seen:
                continue
            seen.add(identity)
            source_group_id = str(ref.get("group_id") or resource_id)
            grouped_refs.setdefault(
                (str(task_id), source_session_id, source_group_id), []
            ).append(ref)

    declarations: list[dict[str, Any]] = []
    for (task_id, source_session_id, source_group_id), refs in grouped_refs.items():
        group_key = "workflow-output:" + hashlib.sha256(
            f"{workflow_id}:{task_id}:{source_session_id}:{source_group_id}".encode()
        ).hexdigest()[:32]
        key_by_id = {
            str(ref.get("resource_id")): str(ref.get("resource_key") or "primary")
            for ref in refs
        }
        for ref in refs:
            resource_id = str(ref.get("resource_id"))
            declarations.append({
                "kind": str(ref.get("kind") or "file"),
                "group_key": group_key,
                "resource_key": str(ref.get("resource_key") or "primary"),
                "parent_key": key_by_id.get(str(ref.get("parent_resource_id") or "")),
                "relation": str(ref.get("relation") or "primary"),
                "role": str(ref.get("role") or "output"),
                "label": str(ref.get("label") or resource_id),
                "locator": dict(ref.get("locator") or {}),
                "format": str(ref.get("format") or "file"),
                "media_type": str(ref.get("media_type") or "application/octet-stream"),
                "renderer": str(ref.get("renderer") or "file"),
                "capabilities": list(ref.get("capabilities") or []),
                "metadata": _metadata_with_origin(
                    ref.get("metadata") if isinstance(ref.get("metadata"), Mapping) else {},
                    {
                        "workflow_id": workflow_id,
                        "source_task_id": task_id,
                        "source_session_id": source_session_id,
                        "source_resource_id": resource_id,
                        "source_group_id": source_group_id,
                    },
                ),
                "tool_name": "run_agent_workflow",
            })
    return declarations
