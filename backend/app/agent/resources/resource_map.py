"""Small, relevance-ranked projection of the durable resource catalog."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .resource_service import StoredResource


_NON_CATALOG_INPUT_TOOLS = {"list_directory", "search_files", "grep", "web_search", "web_fetch"}


def _terms(query: str) -> set[str]:
    return {item.casefold() for item in re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")}


def resource_access_path(item: StoredResource) -> str:
    """Return the canonical absolute path ordinary file tools can use directly."""
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
    return str(resolved)


def _data_shape_fragment(metadata: dict) -> str:
    """数据资源的形状行（来自外置时的 data_shape 元数据）；缺失返回空串。"""
    from app.agent.context.data_shape import render_shape_line

    shape = metadata.get("data_shape") if isinstance(metadata, dict) else None
    if not isinstance(shape, dict) or not shape.get("columns"):
        return ""
    return render_shape_line(shape)


def project_agent_resource_map(
    resources: Iterable[StoredResource],
    *,
    query: str = "",
    max_chars: int = 2400,
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
        f"Resources: {len(active)} catalog rows, {len(projected_items)} unique locators; shown paths are tool-only.",
        "Never place shown paths in final Markdown links or image URLs; users preview and download these outputs, including kind=data files, in the session resource panel.",
        "Search omitted items with list_session_resources; read_session_resource is fallback.",
    ]
    included = 0
    for item, roles in projected_items:
        metadata = item.metadata or {}
        summary = str(metadata.get("summary") or "").strip().replace("\n", " ")[:120]
        mime = str(metadata.get("mime_type") or "")
        details = "; ".join(part for part in (mime, summary) if part)
        line = f"- {item.resource_id} | roles={','.join(roles)} | {item.kind} | {item.label}"
        access_path = resource_access_path(item)
        if access_path:
            line += f" | path={access_path}"
        if details:
            line += f" | {details}"
        shape_line = _data_shape_fragment(metadata)
        if shape_line:
            line += f" | data_shape: {shape_line}"
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
