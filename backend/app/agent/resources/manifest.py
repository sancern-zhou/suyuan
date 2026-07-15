"""Pure merge, filtering, projection, and compatibility behavior."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .models import (
    ResourceImportance,
    ResourceKind,
    ResourceStatus,
    SessionResourceRef,
)


@dataclass(frozen=True)
class LegacyResourceViews:
    data_ids: list[str]
    office_documents: list[dict[str, object]]
    visual_ids: list[str]


def merge_resource_refs(
    existing: list[SessionResourceRef], incoming: list[SessionResourceRef]
) -> list[SessionResourceRef]:
    by_id = {ref.ref_id: ref.model_copy(deep=True) for ref in existing}
    for source in incoming:
        candidate = source.model_copy(deep=True)
        if candidate.logical_key:
            for current in by_id.values():
                if (
                    current.logical_key == candidate.logical_key
                    and current.ref_id != candidate.ref_id
                    and current.status is ResourceStatus.ACTIVE
                ):
                    current.status = ResourceStatus.SUPERSEDED
                    if current.ref_id not in candidate.supersedes:
                        candidate.supersedes.append(current.ref_id)
        previous = by_id.get(candidate.ref_id)
        if previous is not None:
            candidate.created_at = previous.created_at
            candidate.last_used_at = candidate.last_used_at or previous.last_used_at
            if previous.importance is ResourceImportance.PINNED:
                candidate.importance = ResourceImportance.PINNED
            candidate.supersedes = list(dict.fromkeys([*previous.supersedes, *candidate.supersedes]))
        by_id[candidate.ref_id] = candidate
    return sorted(by_id.values(), key=lambda ref: (ref.created_at, ref.ref_id))


def derive_legacy_views(refs: list[SessionResourceRef]) -> LegacyResourceViews:
    active = [ref for ref in refs if ref.status is ResourceStatus.ACTIVE]
    return LegacyResourceViews(
        data_ids=[
            ref.locator.data_id for ref in active
            if ref.kind is ResourceKind.DATA and ref.locator.data_id
        ],
        office_documents=[
            {"file_path": ref.locator.path, "file_name": ref.label, "resource_ref_id": ref.ref_id}
            for ref in active
            if ref.kind in {ResourceKind.FILE, ResourceKind.ARTIFACT} and ref.locator.path
        ],
        visual_ids=[
            ref.locator.visual_id for ref in active
            if ref.kind is ResourceKind.VISUAL and ref.locator.visual_id
        ],
    )


def project_session_resources(
    refs: list[SessionResourceRef], *, query: str, available_tools: set[str], max_chars: int = 8000
) -> str:
    resolver_tool = {
        ResourceKind.DATA: "read_data_registry",
        ResourceKind.FILE: "read_file",
        ResourceKind.ARTIFACT: "present_artifact",
        ResourceKind.URL: "web_fetch",
        ResourceKind.VISUAL: "present_artifact",
    }
    words = {word for word in query.casefold().split() if word}

    def score(ref: SessionResourceRef) -> tuple[int, int, int, str]:
        searchable = " ".join((
            ref.label,
            ref.logical_key or "",
            json.dumps(ref.locator.identity_payload(), ensure_ascii=False),
        )).casefold()
        match = int(any(word in searchable for word in words))
        importance = {ResourceImportance.NORMAL: 0, ResourceImportance.HIGH: 1, ResourceImportance.PINNED: 2}[ref.importance]
        return (
            match,
            importance,
            int(resolver_tool[ref.kind] in available_tools),
            (ref.last_used_at or ref.last_seen_at).isoformat(),
        )

    active = [ref for ref in refs if ref.status is ResourceStatus.ACTIVE]
    active.sort(key=score, reverse=True)
    if not active:
        return ""
    lines = ["Available resources from this session:"]
    included = 0
    for ref in active:
        locator = next(iter(ref.locator.identity_payload().values()))
        line = f"- {ref.ref_id} | {ref.kind.value} | {ref.label} | {locator} | via {resolver_tool[ref.kind]}"
        remaining = len(active) - included - 1
        suffix = f"\n- {remaining} additional resources; use list_session_resources." if remaining else ""
        candidate = "\n".join([*lines, line]) + suffix
        if len(candidate) > max_chars:
            break
        lines.append(line)
        included += 1
    if included < len(active):
        suffix = f"- {len(active) - included} additional resources; use list_session_resources."
        while len("\n".join([*lines, suffix])) > max_chars and len(lines) > 1:
            lines.pop()
            included -= 1
            suffix = f"- {len(active) - included} additional resources; use list_session_resources."
        lines.append(suffix)
    return "\n".join(lines)[:max_chars]


def filter_session_resources(
    refs: list[SessionResourceRef], *, kind: ResourceKind | None = None,
    status: ResourceStatus | None = None, label: str | None = None,
    tool_name: str | None = None, run_id: str | None = None,
    logical_key: str | None = None,
) -> list[SessionResourceRef]:
    label_text = label.casefold() if label else None
    return [
        ref for ref in refs
        if (kind is None or ref.kind is kind)
        and (status is None or ref.status is status)
        and (label_text is None or label_text in ref.label.casefold())
        and (tool_name is None or ref.tool_name == tool_name)
        and (run_id is None or ref.run_id == run_id)
        and (logical_key is None or ref.logical_key == logical_key)
    ]
