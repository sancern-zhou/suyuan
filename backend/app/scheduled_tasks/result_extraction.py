"""Deterministic extraction of structured task results.

Builds a :class:`TaskResult` from the execution record, the executor's
collected agent materials and (when history learning ran) the distilled case.
The distilled values win: the consolidation LLM already normalized
city/station/pollutant names and produced a short conclusion; everything else
falls back to event attributes and mechanical extraction from visuals,
tool-call media/attachments and the final agent response.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models.event import TaskEvent
from .models.execution import TaskExecution
from .models.result import TaskResult

CONCLUSION_MAX_CHARS = 8000

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_DOCUMENT_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".xls", ".csv", ".pptx"}

_DOCUMENT_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:)?[A-Za-z0-9_./\\~-]+\.(?:docx|pdf|xlsx?|csv|pptx)",
    re.IGNORECASE,
)

_REPORT_TOOL_NAMES = {"create_report_package"}

_DIMENSION_ATTRIBUTE_KEYS = {
    "city": ("city", "city_name"),
    "station_id": ("station_id",),
    "station_name": ("station_name", "station"),
    "pollutant": ("pollutant", "target_pollutant"),
}

_EVIDENCE_PATH_KEYS = (
    "evidence_package_path",
    "source_evidence_package_path",
    "evidence_path",
)


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            value = str(value)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _event_attributes(event: TaskEvent | None) -> dict[str, Any]:
    if event is None:
        return {}
    attributes = dict(event.attributes or {})
    payload = event.payload if isinstance(event.payload, dict) else {}
    merge_keys = {
        candidate
        for keys in _DIMENSION_ATTRIBUTE_KEYS.values()
        for candidate in keys
    } | set(_EVIDENCE_PATH_KEYS)
    for key in merge_keys:
        if attributes.get(key) in (None, "") and payload.get(key) is not None:
            attributes[key] = payload[key]
    return attributes


def _dimension_from_case(case: dict | None, field: str) -> str | None:
    if not isinstance(case, dict):
        return None
    return _first_str(case.get(field))


def _dimension_from_distilled(case: dict | None, field: str) -> str | None:
    if not isinstance(case, dict):
        return None
    distilled = case.get("distilled")
    if not isinstance(distilled, dict):
        return None
    values = distilled.get(field)
    if isinstance(values, list) and values:
        return _first_str(values[0])
    return None


def _dimension(
    case: dict | None,
    distilled_field: str,
    case_field: str,
    attributes: dict[str, Any],
    attribute_keys: tuple[str, ...],
) -> str | None:
    return (
        _dimension_from_distilled(case, distilled_field)
        or _dimension_from_case(case, case_field)
        or _first_str(*(attributes.get(key) for key in attribute_keys))
    )


def _extract_findings(case: dict | None) -> list[str]:
    if not isinstance(case, dict):
        return []
    distilled = case.get("distilled")
    if not isinstance(distilled, dict):
        return []
    findings = []
    for item in distilled.get("findings") or []:
        text = _first_str(item)
        if text:
            findings.append(text)
    return findings[:5]


def _extract_evidence_paths(
    case: dict | None,
    attributes: dict[str, Any],
    agent_result: dict | None,
) -> list[str]:
    candidates: list[Any] = [attributes.get(key) for key in _EVIDENCE_PATH_KEYS]

    trigger = (case or {}).get("trigger") or {}
    trigger_attributes = trigger.get("attributes")
    if isinstance(trigger_attributes, dict):
        candidates.extend(trigger_attributes.get(key) for key in _EVIDENCE_PATH_KEYS)

    for call in (agent_result or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        for key in _EVIDENCE_PATH_KEYS:
            candidates.append(data.get(key))

    paths: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        text = _first_str(value)
        if not text:
            continue
        normalized = text.replace("\\", "/")
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
    return paths


def _extract_conclusion(execution: TaskExecution, case: dict | None) -> tuple[str | None, str]:
    case_conclusion = _first_str((case or {}).get("conclusion"))
    if case_conclusion:
        return case_conclusion, "distilled"
    case_summary = _first_str((case or {}).get("summary"))
    if case_summary:
        return case_summary, "summary"
    if execution.steps:
        response = _first_str(execution.steps[-1].agent_response)
        if response:
            return response[:CONCLUSION_MAX_CHARS], "agent_response"
    return None, "none"


def _iter_media_paths(agent_result: dict | None) -> list[str]:
    paths: list[str] = []
    for call in (agent_result or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        for value in (call.get("media") or call.get("attachments") or []):
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
    return paths


def _extract_image_paths(agent_result: dict | None, execution: TaskExecution) -> list[str]:
    paths: list[str] = []
    for visual in (agent_result or {}).get("visuals") or []:
        if isinstance(visual, dict):
            for key in ("local_path", "path", "file_path"):
                candidate = _first_str(visual.get(key))
                if candidate:
                    paths.append(candidate)
                    break
    paths.extend(_iter_media_paths(agent_result))

    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = path.replace("\\", "/")
        suffix = Path(normalized).suffix.lower()
        if suffix not in _IMAGE_EXTENSIONS or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _extract_document_paths(
    agent_result: dict | None,
    execution: TaskExecution,
) -> tuple[list[str], list[dict]]:
    paths: list[str] = []
    report_refs: list[dict] = []
    seen: set[str] = set()

    def _add_path(value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        normalized = value.strip().replace("\\", "/")
        suffix = Path(normalized).suffix.lower()
        if suffix not in _DOCUMENT_EXTENSIONS or normalized in seen:
            return
        seen.add(normalized)
        paths.append(normalized)

    for call in (agent_result or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result")
        data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
        for resource in data.get("resources") or []:
            if isinstance(resource, dict):
                _add_path(resource.get("path"))
        report_id = _first_str(data.get("report_id"))
        if report_id and call.get("tool") in _REPORT_TOOL_NAMES:
            report_refs.append({
                "kind": "report",
                "ref": report_id,
                "title": _first_str(data.get("title") or data.get("report_title")) or report_id,
            })
        for key in ("file_path", "report_dir"):
            candidate = _first_str(data.get(key))
            if candidate:
                report_refs.append({"kind": "report_dir", "ref": candidate})

    for media_path in _iter_media_paths(agent_result):
        _add_path(media_path)

    if execution.steps:
        response = execution.steps[-1].agent_response or ""
        for match in _DOCUMENT_PATH_PATTERN.findall(response):
            _add_path(match)

    unique_report_refs: list[dict] = []
    seen_refs: set[tuple[str, str]] = set()
    for item in report_refs:
        key = (str(item.get("kind")), str(item.get("ref")))
        if key in seen_refs:
            continue
        seen_refs.add(key)
        unique_report_refs.append(item)

    return paths, unique_report_refs[:10]


def extract_task_result(
    execution: TaskExecution,
    event: TaskEvent | None,
    agent_result: dict | None,
    case: dict | None = None,
) -> TaskResult:
    """Build the structured result record for one finished execution."""
    case = case if isinstance(case, dict) else None
    attributes = _event_attributes(event)
    conclusion, conclusion_source = _extract_conclusion(execution, case)
    document_paths, report_refs = _extract_document_paths(agent_result, execution)

    return TaskResult(
        execution_id=execution.execution_id,
        task_id=execution.task_id,
        task_name=execution.task_name,
        session_id=execution.session_id,
        status=execution.status.value,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        city=_dimension(case, "cities", "city", attributes, _DIMENSION_ATTRIBUTE_KEYS["city"]),
        station_id=_dimension(
            case, "stations", "station_id", attributes, _DIMENSION_ATTRIBUTE_KEYS["station_id"]
        ),
        station_name=_dimension(
            case, "stations", "station_name", attributes, _DIMENSION_ATTRIBUTE_KEYS["station_name"]
        ),
        pollutant=_dimension(
            case, "pollutants", "pollutant", attributes, _DIMENSION_ATTRIBUTE_KEYS["pollutant"]
        ),
        conclusion=conclusion,
        conclusion_source=conclusion_source,
        findings=_extract_findings(case),
        image_paths=_extract_image_paths(agent_result, execution),
        document_paths=document_paths,
        evidence_package_paths=_extract_evidence_paths(case, attributes, agent_result),
        report_refs=report_refs,
        trigger_type=execution.trigger_type,
        event_id=execution.event_id,
        event_type=execution.event_type,
        extra={
            "case": case,
            "event_attributes": attributes,
        },
    )
