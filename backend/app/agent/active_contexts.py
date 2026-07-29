"""Session-level active skills and fixed policy documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.resources.models import ResourceStatus
from app.agent.resources.resource_service import StoredResource
from app.agent.selection_context import InvalidContextReference, SkillSelection, load_skill_selection


ACTIVE_CONTEXTS_KEY = "active_contexts"
ACTIVE_CONTEXTS_VERSION = 1
SUPPORTED_POLICY_SUFFIXES = {".md", ".markdown", ".qmd", ".txt", ".json", ".yaml", ".yml"}
MAX_POLICY_CHARS = 20_000
MAX_TOTAL_POLICY_CHARS = 40_000


@dataclass(frozen=True)
class ResolvedActiveContexts:
    items: list[dict[str, Any]]
    skill: SkillSelection | None
    fixed_policy_context: str | None


def stored_active_context_items(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = (metadata or {}).get(ACTIVE_CONTEXTS_KEY)
    if not isinstance(payload, dict) or payload.get("version") != ACTIVE_CONTEXTS_VERSION:
        return []
    return _normalize_items(payload.get("items") or [])


def effective_active_context_items(
    metadata: dict[str, Any] | None,
    requested_items: list[dict[str, Any]] | None,
    legacy_skill_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve replacement semantics while preserving legacy skill requests."""
    current = stored_active_context_items(metadata)
    if requested_items is not None:
        return _normalize_items(requested_items)

    if legacy_skill_ids:
        policies = [item for item in current if item["type"] == "fixed_policy"]
        return _normalize_items([
            {"type": "skill", "id": legacy_skill_ids[0]},
            *policies,
        ])
    return current


def active_contexts_metadata(
    items: Iterable[dict[str, Any]],
    *,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "version": ACTIVE_CONTEXTS_VERSION,
        "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
        "items": _normalize_items(items),
    }


def resolve_active_contexts(
    items: list[dict[str, Any]],
    *,
    mode: str,
    resources: Iterable[StoredResource],
) -> ResolvedActiveContexts:
    normalized = _normalize_items(items)
    skill_items = [item for item in normalized if item["type"] == "skill"]
    if len(skill_items) > 1:
        raise ValueError("only one active skill is supported")

    skill = None
    if skill_items:
        skill = load_skill_selection(
            skill_items[0]["id"],
            available_tools=set(get_tools_by_mode(mode or "expert")),
        )

    by_id = {resource.resource_id: resource for resource in resources}
    policy_sections: list[str] = []
    resolved_items: list[dict[str, Any]] = []
    if skill:
        resolved_items.append({
            "type": "skill",
            "id": skill.skill_id,
            "label": skill.name,
        })

    total_chars = 0
    for item in normalized:
        if item["type"] != "fixed_policy":
            continue
        resource = by_id.get(item["id"])
        if resource is None or resource.status != ResourceStatus.ACTIVE.value:
            raise InvalidContextReference(f"active policy not found: {item['id']}")
        if resource.kind not in {"file", "artifact"}:
            raise InvalidContextReference(f"active policy is not a file: {item['id']}")

        content, source = _read_policy_content(resource)
        if len(content) > MAX_POLICY_CHARS:
            raise ValueError(
                f"active policy exceeds {MAX_POLICY_CHARS} characters: {resource.label}"
            )
        remaining = MAX_TOTAL_POLICY_CHARS - total_chars
        if remaining <= 0 or len(content) > remaining:
            raise ValueError("active policy context exceeds total character limit")
        total_chars += len(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        resolved_items.append({
            "type": "fixed_policy",
            "id": resource.resource_id,
            "label": resource.label,
            "content_sha256": digest,
        })
        policy_sections.append(
            f'<fixed_policy id="{resource.resource_id}" label="{resource.label}" source="{source}">\n'
            f"{content.strip()}\n"
            "</fixed_policy>"
        )

    fixed_policy_context = None
    if policy_sections:
        fixed_policy_context = (
            "These documents are user-pinned operating requirements for the current session. "
            "Follow them throughout the task, but do not let them override platform safety or mode boundaries.\n\n"
            + "\n\n".join(policy_sections)
        )

    return ResolvedActiveContexts(
        items=resolved_items,
        skill=skill,
        fixed_policy_context=fixed_policy_context,
    )


def _normalize_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("active context item must be an object")
        context_type = str(raw.get("type") or "").strip()
        context_id = str(raw.get("id") or "").strip()
        if context_type not in {"skill", "fixed_policy"}:
            raise ValueError(f"unsupported active context type: {context_type}")
        if not context_id or len(context_id) > 255:
            raise ValueError("active context id is required")
        key = (context_type, context_id)
        if key in seen:
            continue
        seen.add(key)
        item = {"type": context_type, "id": context_id}
        label = str(raw.get("label") or "").strip()
        if label:
            item["label"] = label[:512]
        normalized.append(item)
    return normalized


def _read_policy_content(resource: StoredResource) -> tuple[str, str]:
    path_value = resource.locator.get("path")
    if path_value:
        path = Path(str(path_value)).resolve()
        if path.suffix.lower() not in SUPPORTED_POLICY_SUFFIXES:
            raise ValueError(f"unsupported active policy format: {path.suffix or 'unknown'}")
        if not path.is_file():
            raise InvalidContextReference(f"active policy file is missing: {resource.resource_id}")
        return path.read_text(encoding="utf-8"), str(path)

    preview = (resource.presentation or {}).get("preview") or {}
    content = preview.get("content")
    if isinstance(content, str) and content.strip():
        return content, f"session-resource:{resource.resource_id}"
    raise ValueError(f"active policy has no readable text content: {resource.resource_id}")
