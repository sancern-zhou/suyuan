"""Builders for the one explicit resource contract shared by all tools."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterable


def file_resource(
    path: str | Path,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    resource_metadata = {
        "mime_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        **(metadata or {}),
    }
    if resolved.exists() and resolved.is_file():
        resource_metadata.setdefault("size", resolved.stat().st_size)
    resource: dict[str, Any] = {
        "kind": "file",
        "role": role,
        "label": label or resolved.name,
        "locator": {"path": str(resolved)},
        "metadata": resource_metadata,
        "tool_name": tool_name,
    }
    if logical_key:
        resource["logical_key"] = logical_key
    return resource


def data_resource(
    data_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "kind": "data",
        "role": role,
        "label": label or data_id,
        "locator": {"data_id": data_id},
        "metadata": metadata or {},
        "tool_name": tool_name,
    }
    if logical_key:
        resource["logical_key"] = logical_key
    return resource


def artifact_resource(
    artifact_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "kind": "artifact",
        "role": role,
        "label": label or artifact_id,
        "locator": {"artifact_id": artifact_id},
        "metadata": metadata or {},
        "tool_name": tool_name,
    }
    if logical_key:
        resource["logical_key"] = logical_key
    return resource


def visual_resource(
    visual_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "kind": "visual",
        "role": role,
        "label": label or visual_id,
        "locator": {"visual_id": visual_id},
        "metadata": metadata or {},
        "tool_name": tool_name,
    }
    if logical_key:
        resource["logical_key"] = logical_key
    return resource


def resources_for_visuals(
    visuals: Iterable[dict[str, Any]],
    *,
    tool_name: str,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for visual in visuals:
        if not isinstance(visual, dict):
            continue
        payload = visual.get("payload") if isinstance(visual.get("payload"), dict) else {}
        visual_id = str(visual.get("id") or payload.get("image_id") or "").strip()
        if not visual_id or visual_id in seen:
            continue
        resources.append(
            visual_resource(
                visual_id,
                tool_name=tool_name,
                label=str(visual.get("title") or payload.get("title") or visual_id),
                metadata={
                    key: value
                    for key, value in {
                        "type": visual.get("type") or payload.get("type"),
                        "image_url": visual.get("image_url") or payload.get("image_url"),
                    }.items()
                    if value
                },
            )
        )
        seen.add(visual_id)
    return resources


def resources_for_files(
    paths: Iterable[str | Path],
    *,
    tool_name: str,
    role: str = "output",
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        identity = str(resolved)
        if identity in seen or not resolved.is_file():
            continue
        resources.append(file_resource(resolved, tool_name=tool_name, role=role))
        seen.add(identity)
    return resources
