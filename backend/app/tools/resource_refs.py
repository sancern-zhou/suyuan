"""Small helpers for tool-returned resource references."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def build_file_ref(
    path: str | Path,
    *,
    type: Optional[str] = None,
    format: Optional[str] = None,
    size: Optional[int] = None,
    usage: Optional[str] = None,
    preferred_for: Optional[List[str]] = None,
    **metadata: Any,
) -> Dict[str, Any]:
    ref: Dict[str, Any] = {
        "path": str(path),
    }
    if type:
        ref["type"] = type
    if format:
        ref["format"] = format
    if size is not None:
        ref["size"] = size
    if usage:
        ref["usage"] = usage
    if preferred_for:
        ref["preferred_for"] = preferred_for
    for key, value in metadata.items():
        if value is not None:
            ref[key] = value
    return ref


def build_visual_ref(
    *,
    id: Optional[str] = None,
    type: Optional[str] = None,
    title: Optional[str] = None,
    image_url: Optional[str] = None,
    local_path: Optional[str] = None,
    file_path: Optional[str] = None,
    **metadata: Any,
) -> Dict[str, Any]:
    ref: Dict[str, Any] = {}
    for key, value in {
        "id": id,
        "type": type,
        "title": title,
        "image_url": image_url,
        "local_path": local_path,
        "file_path": file_path,
    }.items():
        if value:
            ref[key] = value
    tool_path = local_path or file_path
    if tool_path:
        ref["tool_path"] = tool_path
    for key, value in metadata.items():
        if value is not None:
            ref[key] = value
    return ref


def build_url_ref(url: str, *, usage: str, source: str) -> Dict[str, str]:
    return {
        "url": url,
        "usage": usage,
        "source": source,
    }


def build_data_ref(data_id: str, *, usage: str = "primary") -> Dict[str, str]:
    return {
        "data_id": data_id,
        "usage": usage,
        "tool": "read_data_registry",
    }


def build_data_resume_context(
    *,
    generated_data_ids: Optional[List[str]] = None,
    source_data_ids: Optional[List[str]] = None,
    tool_hint: Optional[str] = None,
) -> Dict[str, Any]:
    source_ids = _unique_strings(source_data_ids or [])
    generated_ids = _unique_strings(generated_data_ids or [])
    refs = {
        "data": [
            *[build_data_ref(data_id, usage="source") for data_id in source_ids],
            *[build_data_ref(data_id, usage="generated") for data_id in generated_ids],
        ]
    }
    llm_resume: Dict[str, Any] = {}
    if source_ids:
        llm_resume["source_data_ids"] = source_ids
    if generated_ids:
        llm_resume["data_ids"] = generated_ids
    if tool_hint:
        llm_resume["tool_hint"] = tool_hint
    elif generated_ids:
        llm_resume["tool_hint"] = (
            f"Use read_data_registry(data_id='{generated_ids[0]}') to inspect the generated data."
        )
    elif source_ids:
        llm_resume["tool_hint"] = (
            f"Use read_data_registry(data_id='{source_ids[0]}') to inspect the source data."
        )
    return {"refs": refs, "llm_resume": llm_resume}


def _unique_strings(values: List[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result


def build_artifact_ref(artifact: Dict[str, Any]) -> Dict[str, Any]:
    ref: Dict[str, Any] = {}
    for key in ("type", "kind", "format", "file_path", "file_name", "title", "mime_type"):
        value = artifact.get(key)
        if value:
            ref[key] = value
    preview = artifact.get("preview")
    if isinstance(preview, dict):
        preview_ref = {
            key: preview.get(key)
            for key in ("html_url", "preview_url", "url", "file_type", "schema_version")
            if preview.get(key)
        }
        if preview_ref:
            ref["preview"] = preview_ref
    return ref


def merge_refs(*refs_list: Optional[Dict[str, List[Dict[str, Any]]]]) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for refs in refs_list:
        if not isinstance(refs, dict):
            continue
        for key, items in refs.items():
            if not isinstance(items, list):
                continue
            bucket = merged.setdefault(key, [])
            for item in items:
                if isinstance(item, dict) and item not in bucket:
                    bucket.append(item)
    return merged
