"""Normalize explicit and narrowly-defined compatibility resource references."""
from __future__ import annotations

from typing import Any

from .models import (
    ResourceImportance,
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    SessionResourceRef,
)

BUCKET_KINDS = {
    "data": ResourceKind.DATA,
    "files": ResourceKind.FILE,
    "artifacts": ResourceKind.ARTIFACT,
    "urls": ResourceKind.URL,
    "visuals": ResourceKind.VISUAL,
}

COMPATIBILITY_FIELDS = {
    "data_id": (ResourceKind.DATA, "data_id"),
    "report_data_id": (ResourceKind.DATA, "data_id"),
    "file_path": (ResourceKind.FILE, "path"),
    "local_path": (ResourceKind.FILE, "path"),
    "url": (ResourceKind.URL, "url"),
    "artifact_id": (ResourceKind.ARTIFACT, "artifact_id"),
    "visual_id": (ResourceKind.VISUAL, "visual_id"),
}


def _locator_for(kind: ResourceKind, item: dict[str, Any]) -> ResourceLocator:
    if kind is ResourceKind.DATA:
        return ResourceLocator(data_id=item.get("data_id") or item.get("id"))
    if kind is ResourceKind.FILE:
        return ResourceLocator(path=item.get("path") or item.get("file_path") or item.get("local_path"))
    if kind is ResourceKind.URL:
        return ResourceLocator(url=item.get("url"))
    if kind is ResourceKind.VISUAL:
        return ResourceLocator(visual_id=item.get("visual_id") or item.get("id"))
    artifact_id = item.get("artifact_id") or item.get("id")
    if artifact_id:
        return ResourceLocator(artifact_id=artifact_id)
    return ResourceLocator(path=item.get("path") or item.get("file_path"))


def _make_ref(
    *,
    kind: ResourceKind,
    item: dict[str, Any],
    tool_name: str,
    run_id: str,
    turn_sequence: int,
) -> SessionResourceRef:
    locator = _locator_for(kind, item)
    identity = next(iter(locator.identity_payload().values()))
    known = {
        "data_id", "id", "path", "file_path", "local_path", "url", "artifact_id",
        "visual_id", "logical_key", "role", "label", "importance",
    }
    return SessionResourceRef.create(
        kind=kind,
        locator=locator,
        logical_key=item.get("logical_key"),
        role=ResourceRole(item.get("role", "output")),
        label=str(item.get("label") or item.get("title") or identity),
        importance=ResourceImportance(item.get("importance", "normal")),
        tool_name=tool_name,
        run_id=run_id,
        turn_sequence=turn_sequence,
        metadata={key: value for key, value in item.items() if key not in known},
    )


def normalize_tool_result_refs(
    *,
    tool_name: str,
    run_id: str,
    turn_sequence: int,
    result: Any,
) -> tuple[list[SessionResourceRef], list[dict[str, str]]]:
    if not isinstance(result, dict):
        return [], []

    refs: list[SessionResourceRef] = []
    rejected: list[dict[str, str]] = []
    explicit = result.get("refs")
    if isinstance(explicit, dict):
        for bucket, kind in BUCKET_KINDS.items():
            items = explicit.get(bucket, [])
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    rejected.append({"field": f"refs.{bucket}[{index}]", "reason": "not_an_object"})
                    continue
                try:
                    refs.append(_make_ref(
                        kind=kind,
                        item=item,
                        tool_name=tool_name,
                        run_id=run_id,
                        turn_sequence=turn_sequence,
                    ))
                except (TypeError, ValueError) as exc:
                    rejected.append({"field": f"refs.{bucket}[{index}]", "reason": str(exc)[:200]})
        return refs, rejected

    containers = [result]
    if isinstance(result.get("data"), dict):
        containers.append(result["data"])
    for container in containers:
        for field, (kind, locator_field) in COMPATIBILITY_FIELDS.items():
            value = container.get(field)
            if isinstance(value, str) and value:
                refs.append(_make_ref(
                    kind=kind,
                    item={locator_field: value, "label": field},
                    tool_name=tool_name,
                    run_id=run_id,
                    turn_sequence=turn_sequence,
                ))
        for field in ("data_ids", "report_data_ids", "source_data_ids"):
            values = container.get(field)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value:
                        refs.append(_make_ref(
                            kind=ResourceKind.DATA,
                            item={"data_id": value, "label": field},
                            tool_name=tool_name,
                            run_id=run_id,
                            turn_sequence=turn_sequence,
                        ))
    visuals = result.get("visuals")
    if isinstance(visuals, list):
        for item in visuals:
            if isinstance(item, dict) and (item.get("id") or item.get("visual_id")):
                refs.append(_make_ref(
                    kind=ResourceKind.VISUAL,
                    item=item,
                    tool_name=tool_name,
                    run_id=run_id,
                    turn_sequence=turn_sequence,
                ))
    unique = {ref.ref_id: ref for ref in refs}
    return list(unique.values()), rejected
