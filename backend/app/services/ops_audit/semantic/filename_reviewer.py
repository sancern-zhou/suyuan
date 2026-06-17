"""LLM filename semantic review for attachment evidence categories."""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.semantic.prompts import FILENAME_SEMANTIC_JSON_PROMPT
from app.services.ops_audit.semantic.reviewer import _call_semantic_llm_json


STATION_MAINTAIN_TYPE_DEFINITIONS = {
    "particle_clock_photo": "颗粒物仪器时钟、时间、显示数据或颗粒物仪器检查相关现场照片",
    "data_logger_clock_photo": "数据采集仪、数采仪时钟、时间、显示数据或时间一致性相关现场照片",
    "filter_cleaning_photo": "空调滤网、仪器防尘网、过滤网、滤膜网清洗相关现场照片",
}


def review_station_maintenance_filename_semantics(
    items: list[dict[str, Any]],
    required_types: list[str],
    *,
    working_order_code: str | None = None,
    requirement_id: str | None = None,
) -> dict[str, Any] | None:
    """Ask the LLM whether attachment filenames cover station-maintenance evidence types."""

    filenames = _attachment_filenames(items)
    semantic_required_types = [item for item in required_types if item in STATION_MAINTAIN_TYPE_DEFINITIONS]
    if not filenames or not semantic_required_types:
        return None

    raw = _call_semantic_llm_json(
        FILENAME_SEMANTIC_JSON_PROMPT,
        json.dumps({"filenames": filenames}, ensure_ascii=False),
        context={
            "working_order_code": working_order_code,
            "requirement_id": requirement_id,
            "required_types": semantic_required_types,
            "type_definitions": {
                key: STATION_MAINTAIN_TYPE_DEFINITIONS[key]
                for key in semantic_required_types
            },
        },
    )
    if not raw:
        return None
    return _normalize_filename_semantic_result(raw, semantic_required_types, filenames)


def _attachment_filenames(items: list[dict[str, Any]]) -> list[str]:
    filenames: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.get("name") or item.get("descriptor")
        filename = str(value or "").strip()
        if not filename or filename in seen:
            continue
        seen.add(filename)
        filenames.append(filename[:300])
    return filenames[:50]


def _normalize_filename_semantic_result(
    raw: dict[str, Any],
    required_types: list[str],
    filenames: list[str],
) -> dict[str, Any]:
    covered_types = _normalize_covered_types(raw.get("covered_types"), required_types, filenames)
    missing_types = _normalize_type_list(raw.get("missing_types"), required_types)
    uncertain_types = _normalize_type_list(raw.get("uncertain_types"), required_types)

    for attachment_type in required_types:
        if attachment_type in covered_types:
            if attachment_type in missing_types:
                missing_types.remove(attachment_type)
            continue
        if attachment_type not in missing_types and attachment_type not in uncertain_types:
            uncertain_types.append(attachment_type)

    evidence = raw.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []

    return {
        "covered_types": covered_types,
        "missing_types": missing_types,
        "uncertain_types": uncertain_types,
        "evidence": evidence[:20],
        "confidence": _bounded_confidence(raw.get("confidence"), default=0.65),
    }


def _normalize_covered_types(value: Any, required_types: list[str], filenames: list[str]) -> dict[str, list[str]]:
    allowed_types = set(required_types)
    allowed_names = set(filenames)
    covered: dict[str, list[str]] = {}
    if not isinstance(value, dict):
        return covered
    for attachment_type, matched_names in value.items():
        key = str(attachment_type)
        if key not in allowed_types:
            continue
        if isinstance(matched_names, str):
            names = [matched_names]
        elif isinstance(matched_names, list):
            names = [str(name) for name in matched_names if str(name).strip()]
        else:
            names = []
        covered[key] = [name for name in names if name in allowed_names] or names[:5]
    return covered


def _normalize_type_list(value: Any, required_types: list[str]) -> list[str]:
    allowed = set(required_types)
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item) for item in values if str(item) in allowed]


def _bounded_confidence(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(0.0, min(1.0, number)), 2)
