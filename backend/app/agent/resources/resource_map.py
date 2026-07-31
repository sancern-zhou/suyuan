"""Small, relevance-ranked projection of the durable resource catalog."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from app.utils.path_config import BACKEND_ROOT

from .resource_service import StoredResource


_NON_CATALOG_INPUT_TOOLS = {"list_directory", "search_files", "grep", "web_search", "web_fetch"}


def _terms(query: str) -> set[str]:
    return {item.casefold() for item in re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")}


def _access_path(item: StoredResource) -> str:
    """Return the shortest path that the Agent's file tools can use directly."""
    raw_path = str((item.locator or {}).get("path") or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return ""
    if not resolved.exists():
        return ""
    try:
        return str(resolved.relative_to(Path(BACKEND_ROOT).resolve()))
    except ValueError:
        return str(resolved)


def project_agent_resource_map(
    resources: Iterable[StoredResource],
    *,
    query: str = "",
    max_chars: int = 1800,
    max_items: int = 12,
) -> str:
    """Return a bounded, directly actionable index without resource bodies."""
    active = [
        item
        for item in resources
        if item.status == "active"
        and not (item.role == "source" and item.tool_name in _NON_CATALOG_INPUT_TOOLS)
    ]
    if not active:
        return ""
    terms = _terms(query)

    # Keep role-separated rows in the durable catalog, but avoid spending
    # prompt space on the same physical locator more than once. The projected
    # line still reports every role represented by that locator.
    grouped: dict[tuple[tuple[str, str], ...], list[StoredResource]] = {}
    for item in active:
        locator_key = tuple(sorted((str(key), str(value)) for key, value in (item.locator or {}).items()))
        grouped.setdefault(locator_key or (("resource_id", item.resource_id),), []).append(item)

    role_priority = {"attachment": 4, "primary": 3, "report": 3, "output": 2, "source": 1}
    projected_items: list[tuple[StoredResource, list[str]]] = []
    for candidates in grouped.values():
        representative = max(
            candidates,
            key=lambda item: (role_priority.get(item.role, 0), item.turn_sequence, item.updated_at),
        )
        roles = sorted({item.role for item in candidates}, key=lambda role: -role_priority.get(role, 0))
        projected_items.append((representative, roles))

    def score(entry: tuple[StoredResource, list[str]]):
        item, roles = entry
        summary = str((item.metadata or {}).get("summary") or "")
        searchable = f"{item.label} {item.resource_key} {summary}".casefold()
        relevance = sum(term in searchable for term in terms)
        role = max((role_priority.get(value, 0) for value in roles), default=0)
        return relevance, role, item.turn_sequence, item.updated_at

    projected_items.sort(key=score, reverse=True)
    lines = [
        f"Resources: {len(active)} catalog rows, {len(projected_items)} unique locators; shown paths are directly usable.",
        "Search omitted items with list_session_resources; read_session_resource is fallback.",
    ]
    included = 0
    for item, roles in projected_items:
        summary = str((item.metadata or {}).get("summary") or "").strip().replace("\n", " ")[:120]
        mime = str((item.metadata or {}).get("mime_type") or "")
        details = "; ".join(part for part in (mime, summary) if part)
        line = f"- {item.resource_id} | roles={','.join(roles)} | {item.kind} | {item.label}"
        access_path = _access_path(item)
        if access_path:
            line += f" | path={access_path}"
        if details:
            line += f" | {details}"
        if len("\n".join([*lines, line])) > max_chars or included >= max_items:
            break
        lines.append(line)
        included += 1
    remaining = len(projected_items) - included
    if remaining:
        suffix = f"- +{remaining} more; search on demand."
        if len("\n".join([*lines, suffix])) <= max_chars:
            lines.append(suffix)
    return "\n".join(lines)
