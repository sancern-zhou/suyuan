"""Explicit grouped-resource builders shared by tool producers."""
from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _file_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "file"


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _path_group_key(path: Path, tool_name: str) -> str:
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    return f"{tool_name}:file:{digest}"


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if "path" not in key.lower() and "url" not in key.lower()
    }


def primary_file(
    path: str | Path,
    *,
    group_key: str,
    tool_name: str,
    role: str = "output",
    renderer: str = "file",
    capabilities: Iterable[str] = ("download",),
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    resource_metadata = _safe_metadata(metadata)
    if resolved.is_file():
        resource_metadata.setdefault("size", resolved.stat().st_size)
    file_format = _file_format(resolved)
    return {
        "kind": "file",
        "group_key": group_key,
        "resource_key": f"primary:{file_format}",
        "relation": "primary",
        "role": role,
        "label": label or resolved.name,
        "locator": {"path": str(resolved)},
        "format": file_format,
        "media_type": _media_type(resolved),
        "renderer": renderer,
        "capabilities": list(capabilities),
        "metadata": resource_metadata,
        "tool_name": tool_name,
    }


def derivative_file(
    path: str | Path,
    *,
    group_key: str,
    parent_key: str,
    tool_name: str,
    relation: str = "preview",
    role: str = "output",
    renderer: str = "file",
    capabilities: Iterable[str] = ("preview", "download"),
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    file_format = _file_format(resolved)
    key_digest = hashlib.sha256(resolved.name.encode()).hexdigest()[:10]
    resource_metadata = _safe_metadata(metadata)
    if resolved.is_file():
        resource_metadata.setdefault("size", resolved.stat().st_size)
    return {
        "kind": "file",
        "group_key": group_key,
        "resource_key": f"{relation}:{file_format}:{key_digest}",
        "parent_key": parent_key,
        "relation": relation,
        "role": role,
        "label": label or resolved.name,
        "locator": {"path": str(resolved)},
        "format": file_format,
        "media_type": _media_type(resolved),
        "renderer": renderer,
        "capabilities": list(capabilities),
        "metadata": resource_metadata,
        "tool_name": tool_name,
    }


def preview_file(
    path: str | Path,
    *,
    renderer: str,
    capabilities: Iterable[str] = ("preview", "download"),
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe a preview before it is bound into a file product."""
    return {
        "path": str(Path(path).expanduser().resolve()),
        "renderer": renderer,
        "capabilities": list(capabilities),
        "metadata": _safe_metadata(metadata),
    }


def file_product(
    *,
    primary_path: str | Path,
    group_key: str,
    tool_name: str,
    previews: Iterable[dict[str, Any]] = (),
    role: str = "output",
    renderer: str = "file",
    capabilities: Iterable[str] = ("download",),
) -> list[dict[str, Any]]:
    primary = primary_file(
        primary_path,
        group_key=group_key,
        tool_name=tool_name,
        role=role,
        renderer=renderer,
        capabilities=capabilities,
    )
    members = [primary]
    for preview in previews:
        members.append(
            derivative_file(
                preview["path"],
                group_key=group_key,
                parent_key=primary["resource_key"],
                tool_name=tool_name,
                relation="preview",
                role=role,
                renderer=str(preview.get("renderer") or "file"),
                capabilities=preview.get("capabilities")
                or ("preview", "download"),
                metadata=preview.get("metadata"),
            )
        )
    return members


def directory_artifact(
    path: str | Path,
    *,
    entrypoint: str,
    group_key: str,
    tool_name: str,
    role: str = "output",
    renderer: str = "html",
    capabilities: Iterable[str] = ("preview",),
    label: str | None = None,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    entrypoint_path = (resolved / entrypoint).resolve()
    if not entrypoint_path.is_relative_to(resolved):
        raise ValueError("artifact entrypoint must stay inside its directory")
    file_format = _file_format(entrypoint_path)
    return {
        "kind": "artifact",
        "group_key": group_key,
        "resource_key": f"primary:{file_format}",
        "relation": "primary",
        "role": role,
        "label": label or resolved.name,
        "locator": {"path": str(resolved)},
        "format": file_format,
        "media_type": _media_type(entrypoint_path),
        "renderer": renderer,
        "capabilities": list(capabilities),
        "metadata": {"entrypoint": str(entrypoint_path.relative_to(resolved))},
        "tool_name": tool_name,
    }


def data_resource(
    data_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    group_key = logical_key or f"data:{data_id}"
    return {
        "kind": "data",
        "group_key": group_key,
        "resource_key": "primary:data",
        "relation": "primary",
        "role": role,
        "label": label or data_id,
        "locator": {"data_id": data_id},
        "format": "data",
        "media_type": "application/vnd.suyuan.data",
        "renderer": "file",
        "capabilities": [],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


def artifact_resource(
    artifact_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "artifact",
        "group_key": logical_key or f"artifact:{artifact_id}",
        "resource_key": "primary:artifact",
        "relation": "primary",
        "role": role,
        "label": label or artifact_id,
        "locator": {"artifact_id": artifact_id},
        "format": "artifact",
        "media_type": "application/vnd.suyuan.artifact",
        "renderer": "file",
        "capabilities": [],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


def chart_resource(
    visual_id: str,
    *,
    group_key: str,
    tool_name: str,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "visual",
        "group_key": group_key,
        "resource_key": "primary:chart",
        "relation": "primary",
        "role": "output",
        "label": label or visual_id,
        "locator": {"visual_id": visual_id},
        "format": "chart",
        "media_type": "application/vnd.suyuan.chart+json",
        "renderer": "chart",
        "capabilities": ["preview"],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


def board_resource(
    artifact_id: str,
    *,
    group_key: str,
    tool_name: str,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "artifact",
        "group_key": group_key,
        "resource_key": "primary:board",
        "relation": "primary",
        "role": "output",
        "label": label or artifact_id,
        "locator": {"artifact_id": artifact_id},
        "format": "drawio",
        "media_type": "application/vnd.jgraph.mxfile",
        "renderer": "board",
        "capabilities": ["preview", "edit"],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


def visual_resource(
    visual_id: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource = chart_resource(
        visual_id,
        group_key=logical_key or f"visual:{visual_id}",
        tool_name=tool_name,
        label=label,
        metadata=metadata,
    )
    resource["role"] = role
    return resource


def resources_for_visuals(
    visuals: Iterable[dict[str, Any]], *, tool_name: str
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
                metadata={"type": visual.get("type") or payload.get("type")},
            )
        )
        seen.add(visual_id)
    return resources


# Temporary call-site adapters. Tasks 5-7 remove every import before the final
# hard cut; their output is already the canonical grouped contract.
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
    return primary_file(
        resolved,
        group_key=logical_key or _path_group_key(resolved, tool_name),
        tool_name=tool_name,
        role=role,
        label=label,
        metadata=metadata,
    )


def resources_for_files(
    paths: Iterable[str | Path], *, tool_name: str, role: str = "output"
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        identity = str(resolved)
        if identity in seen or not resolved.is_file():
            continue
        resources.append(
            primary_file(
                resolved,
                group_key=_path_group_key(resolved, tool_name),
                tool_name=tool_name,
                role=role,
            )
        )
        seen.add(identity)
    return resources
