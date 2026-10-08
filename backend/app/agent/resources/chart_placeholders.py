"""Normalize ``[[chart:...]]`` placeholders in final answers.

The chat protocol requires ``[[chart:<visual_id>]]`` where ``visual_id`` is the
``visuals[].id`` returned by chart tools. Models sometimes copy the catalog
``resource_id`` instead (for example from ``list_session_resources`` output or
an exported resource manifest). The frontend resolves chart placeholders by
``visual_id`` only, so resource-id placeholders stay as literal text and the
charts never render. This module rewrites resource-id placeholders into visual
ids before the answer is persisted and emitted.
"""
from __future__ import annotations

import re
from typing import Optional

import structlog

from app.agent.resources.resource_service import SessionResourceService

logger = structlog.get_logger(__name__)

CHART_PLACEHOLDER_PATTERN = re.compile(r"\[\[chart:([A-Za-z0-9_.:-]{1,200})\]\]")

_MAX_SCAN_PAGES = 50
_PAGE_SIZE = 100


def collect_placeholder_ids(text: str) -> set[str]:
    return {match.group(1) for match in CHART_PLACEHOLDER_PATTERN.finditer(text or "")}


async def _resource_id_to_visual_id(
    session_id: str,
    candidate_ids: set[str],
    service: SessionResourceService,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cursor: Optional[str] = None
    for _ in range(_MAX_SCAN_PAGES):
        page = await service.list_resources(
            session_id, status="active", limit=_PAGE_SIZE, cursor=cursor
        )
        for resource in page.resources:
            if resource.resource_id not in candidate_ids:
                continue
            visual_id = str((resource.metadata or {}).get("visual_id") or "").strip()
            if visual_id and visual_id != resource.resource_id:
                mapping[resource.resource_id] = visual_id
        cursor = page.next_cursor
        if not cursor:
            break
    return mapping


async def normalize_chart_placeholders(
    text: str,
    session_id: str | None,
    service: SessionResourceService | None = None,
) -> str:
    """Rewrite ``[[chart:<resource_id>]]`` to ``[[chart:<visual_id>]]``.

    Placeholders that already use a visual id (or an unknown id) are kept
    unchanged. Fail-open: any catalog lookup problem returns the original text.
    """
    if not text or "[[chart:" not in text or not session_id:
        return text
    candidate_ids = collect_placeholder_ids(text)
    if not candidate_ids:
        return text
    try:
        active_service = service or SessionResourceService.database()
        mapping = await _resource_id_to_visual_id(session_id, candidate_ids, active_service)
    except Exception as exc:
        logger.warning(
            "chart_placeholder_normalize_lookup_failed",
            session_id=session_id,
            error=str(exc),
        )
        return text
    if not mapping:
        return text
    normalized = CHART_PLACEHOLDER_PATTERN.sub(
        lambda match: f"[[chart:{mapping.get(match.group(1), match.group(1))}]]",
        text,
    )
    logger.info(
        "chart_placeholder_normalized",
        session_id=session_id,
        rewritten=sorted(mapping),
    )
    return normalized
