"""Explicit grouped-resource builders shared by tool producers."""
from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.utils.path_config import get_data_registry
from app.agent.context.data_files import resolve_data_path


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


def _safe_spec_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [_safe_spec_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _safe_spec_payload(item)
            for key, item in value.items()
            if "path" not in key.lower()
            and "url" not in key.lower()
            and "base64" not in key.lower()
        }
    return value


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


def data_file_resource(
    file_path: str,
    *,
    tool_name: str,
    role: str = "output",
    label: str | None = None,
    logical_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_data_path(file_path)
    group_key = logical_key or _path_group_key(resolved, tool_name)
    return {
        "kind": "data",
        "group_key": group_key,
        "resource_key": "primary:data",
        "relation": "primary",
        "role": role,
        "label": label or resolved.name,
        "locator": {"path": str(resolved)},
        "format": _file_format(resolved),
        "media_type": _media_type(resolved),
        "renderer": "file",
        "capabilities": ["preview", "download"],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


# Internal source compatibility for producers not yet renamed. It creates the
# same path-backed resource and does not expose a second data identity.
data_resource = data_file_resource


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
    path: str | Path | None = None,
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
        "locator": {"path": str(Path(path).expanduser().resolve())}
        if path is not None
        else {"visual_id": visual_id},
        "format": "json",
        "media_type": "application/json",
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
    path: str | Path | None = None,
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
        "locator": {"path": str(Path(path).expanduser().resolve())}
        if path is not None
        else {"artifact_id": artifact_id},
        "format": "drawio",
        "media_type": "application/xml",
        "renderer": "board",
        "capabilities": ["preview", "edit"],
        "metadata": _safe_metadata(metadata),
        "tool_name": tool_name,
    }


def board_product(
    *,
    xml_path: str | Path,
    artifact_id: str,
    tool_name: str,
    screenshot_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    group_key = f"board:{artifact_id}"
    board = board_resource(
        artifact_id,
        path=xml_path,
        group_key=group_key,
        tool_name=tool_name,
    )
    board["resource_key"] = "board-xml"
    members = [board]
    if screenshot_path is not None:
        screenshot = derivative_file(
            screenshot_path,
            group_key=group_key,
            parent_key="board-xml",
            tool_name=tool_name,
            relation="preview",
            renderer="image",
        )
        screenshot["resource_key"] = "board-preview"
        members.append(screenshot)
    return members


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
        chart_dir = (get_data_registry() / "charts").resolve()
        chart_dir.mkdir(parents=True, exist_ok=True)
        spec_path = chart_dir / f"{visual_id}.json"
        safe_spec = _safe_spec_payload(visual)
        spec_path.write_text(
            json.dumps(safe_spec, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        group_key = f"visual:{visual_id}"
        chart = chart_resource(
            visual_id,
            path=spec_path,
            group_key=group_key,
            tool_name=tool_name,
            label=str(visual.get("title") or payload.get("title") or visual_id),
            metadata={"type": visual.get("type") or payload.get("type")},
        )
        chart["resource_key"] = "chart-spec"
        resources.append(chart)
        data = visual.get("data") if isinstance(visual.get("data"), dict) else {}
        meta = visual.get("meta") if isinstance(visual.get("meta"), dict) else {}
        static_preview = (
            meta.get("static_preview")
            if isinstance(meta.get("static_preview"), dict)
            else {}
        )
        raw_image_path = (
            visual.get("local_path")
            or visual.get("file_path")
            or payload.get("local_path")
            or payload.get("file_path")
            or data.get("local_path")
            or data.get("file_path")
            or data.get("source_file_path")
            or meta.get("local_path")
            or meta.get("file_path")
            or static_preview.get("local_path")
        )
        if isinstance(raw_image_path, str):
            image_path = Path(raw_image_path).expanduser().resolve()
            if image_path.is_file():
                image = derivative_file(
                    image_path,
                    group_key=group_key,
                    parent_key="chart-spec",
                    tool_name=tool_name,
                    relation="rendition",
                    renderer="image",
                )
                image["resource_key"] = "chart-image"
                resources.append(image)
        seen.add(visual_id)
    return resources


def generated_file_products(
    paths: Iterable[str | Path],
    *,
    tool_name: str,
    preview_paths: dict[str, str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Declare generated files with renderer/capability-aware resource groups."""
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    previews = {
        str(Path(primary).expanduser().resolve()): Path(preview).expanduser().resolve()
        for primary, preview in (preview_paths or {}).items()
        if primary and preview
    }
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        identity = str(resolved)
        if identity in seen or not resolved.is_file():
            continue
        suffix = resolved.suffix.lower()
        renderer = "file"
        capabilities: tuple[str, ...] = ("download",)
        if suffix == ".pdf":
            renderer, capabilities = "pdf", ("preview", "download")
        elif suffix in {".html", ".htm"}:
            renderer, capabilities = "html", ("preview", "download")
        elif suffix in {".md", ".qmd"}:
            renderer, capabilities = "markdown", ("preview", "download")
        elif suffix in {".xlsx", ".xls"}:
            renderer, capabilities = "spreadsheet", ("preview", "download", "edit")
        elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}:
            renderer, capabilities = "image", ("preview", "download")
        elif suffix in {".ppt", ".pptx"}:
            capabilities = ("download",)

        group_key = _path_group_key(resolved, tool_name)
        preview_path = previews.get(identity)
        preview_specs = []
        if preview_path is not None and preview_path.is_file():
            preview_specs.append(
                preview_file(
                    preview_path,
                    renderer="pdf" if preview_path.suffix.lower() == ".pdf" else "file",
                    capabilities=("preview", "download"),
                )
            )
        resources.extend(
            file_product(
                primary_path=resolved,
                group_key=group_key,
                tool_name=tool_name,
                previews=preview_specs,
                renderer=renderer,
                capabilities=capabilities,
            )
        )
        seen.add(identity)
    return resources


def single_file_product(
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


def file_products(
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
