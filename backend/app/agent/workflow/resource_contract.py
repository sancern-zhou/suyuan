"""Explicit resource compatibility checks before downstream model execution."""

import csv
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils.path_config import resolve_agent_path


class ResourceContractError(ValueError):
    def __init__(self, violations: list[dict[str, Any]]):
        self.violations = violations
        super().__init__("resource contract violations: " + json.dumps(violations, ensure_ascii=False))


_KEYS = {"source_task_id", "required", "kind", "format", "fields", "units", "granularity", "time_range", "scope"}


def result_handles(task_id: str, result: Any) -> list[dict[str, Any]]:
    from .lineage import _result_envelope
    if not isinstance(result, Mapping):
        return []
    data = result.get("data") if isinstance(result.get("data"), Mapping) else {}
    handles, seen = [], set()
    for ref in [*(data.get("resource_refs") or []), *(_result_envelope(result).get("artifacts") or [])]:
        if isinstance(ref, Mapping) and ref.get("resource_id") and ref.get("source_session_id"):
            identity = (ref["source_session_id"], ref["resource_id"])
            if identity not in seen:
                handles.append({**ref, "handle_type": "session_resource", "source_task_id": task_id})
                seen.add(identity)
                path = ref.get("file_path") or (ref.get("locator") or {}).get("path")
                if path:
                    seen.add(("file_path", str(path)))
    files = [(path, "file", None) for path in data.get("file_paths") or []]
    files += [(data.get(key), "file", None) for key in ("file_path", "report_file_path")]
    for artifact in _result_envelope(result).get("artifacts") or []:
        if isinstance(artifact, Mapping):
            if not artifact.get("resource_id"):
                files.append((artifact.get("path") or artifact.get("file_path"), artifact.get("kind") or "artifact", artifact.get("name")))
        else:
            files.append((artifact, "artifact", None))
    for path, kind, name in files:
        if path and ("file_path", str(path)) not in seen:
            handles.append({"source_task_id": task_id, "handle_type": "file_path", "kind": kind, "file_path": str(path),
                            **({"label": str(name)} if name else {})})
            seen.add(("file_path", str(path)))
    return handles


def validate_contract_definition(contract: Mapping[str, Any], dependencies: tuple[str, ...] | None = None) -> None:
    if not isinstance(contract, Mapping) or set(contract) - _KEYS:
        raise ValueError("invalid resource contract fields")
    if dependencies is not None and contract.get("source_task_id") not in dependencies:
        raise ValueError("resource contract source must be a direct dependency")
    if dependencies is None and "source_task_id" in contract:
        raise ValueError("output resource contract cannot declare an input source")
    if "required" in contract and not isinstance(contract["required"], bool):
        raise ValueError("resource contract required must be boolean")
    if "fields" in contract and (not isinstance(contract["fields"], list) or any(not isinstance(v, str) for v in contract["fields"])):
        raise ValueError("resource contract fields must be a string list")
    if "units" in contract and (not isinstance(contract["units"], Mapping) or any(not isinstance(v, str) for v in contract["units"].values())):
        raise ValueError("resource contract units must map fields to units")
    for key in ("kind", "format", "granularity"):
        if key in contract and (not isinstance(contract[key], str) or not contract[key]):
            raise ValueError(f"resource contract {key} must be a nonempty string")
    if "scope" in contract and not isinstance(contract["scope"], Mapping):
        raise ValueError("resource contract scope must be an object")
    if "time_range" in contract:
        value = contract["time_range"]
        if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
            raise ValueError("resource time_range requires start and end")
        try:
            if _date(value["start"]) > _date(value["end"]):
                raise ValueError("resource time_range is reversed")
        except (TypeError, ValueError) as exc:
            raise ValueError("resource time_range requires ordered ISO timestamps") from exc


def _date(value: Any) -> datetime:
    from datetime import timezone
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _file_fields(path: Path) -> set[str] | None:
    """Bounded inspection; large JSON requires explicit catalog schema metadata."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = stream.readline(65537)
        if len(header) > 65536:
            raise ValueError("CSV header exceeds inspection limit")
        return set(next(csv.reader([header]), []))
    if path.suffix.lower() == ".json" and path.stat().st_size <= 2 * 1024 * 1024:
        value = json.loads(path.read_text(encoding="utf-8"))
        for _ in range(4):
            if not isinstance(value, Mapping):
                break
            nested = next((value[key] for key in ("records", "rows", "data") if isinstance(value.get(key), (list, dict))), None)
            if nested is None:
                break
            value = nested
        if isinstance(value, list):
            fields = None
            for row in value:
                if not isinstance(row, Mapping):
                    return set()
                fields = set(row) if fields is None else fields.intersection(row)
            return fields or set()
        if isinstance(value, Mapping):
            return set(value)
    return None


def _check(contract: Mapping[str, Any], handle: Mapping[str, Any]) -> list[str]:
    metadata = handle.get("metadata") or {}
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("data_contract", {}), Mapping):
        return ["resource schema metadata is invalid"]
    actual = dict(metadata.get("data_contract") or {})
    # Existing data producers already publish typed column metadata. Reuse it
    # for large files; never infer units or business scope from column names.
    shape = metadata.get("data_shape")
    if "fields" not in actual and isinstance(shape, Mapping):
        columns = shape.get("columns") or []
        if isinstance(columns, list) and all(isinstance(item, Mapping) and isinstance(item.get("name"), str) for item in columns):
            actual["fields"] = [item["name"] for item in columns]
    if "fields" in actual and (not isinstance(actual["fields"], list) or any(not isinstance(field, str) for field in actual["fields"])):
        return ["resource fields metadata is invalid"]
    actual.update({key: handle[key] for key in ("kind", "format") if handle.get(key)})
    path_text = handle.get("file_path") or (handle.get("locator") or {}).get("path")
    fields = None
    if path_text:
        try:
            path = resolve_agent_path(path_text)
            if not path.is_file():
                return ["resource file is missing"]
            actual.setdefault("format", path.suffix.lstrip(".").lower())
            if actual.get("kind") == "file" and handle.get("handle_type") == "file_path" and contract.get("kind") == "data" and path.suffix.lower() in {".json", ".csv"}:
                actual["kind"] = "data"
            if contract.get("fields"):
                fields = _file_fields(path)
        except (OSError, ValueError, TypeError) as exc:
            return [f"resource file cannot be validated: {exc}"]
    elif not (handle.get("locator") or {}).get("uri"):
        return ["resource has no usable locator"]
    errors = []
    for key in ("kind", "format", "granularity"):
        if key in contract and actual.get(key) != contract[key]:
            errors.append(f"{key}: expected {contract[key]}, got {actual.get(key)}")
    available = fields if fields is not None else set(actual.get("fields") or [])
    missing = set(contract.get("fields") or []) - available
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    for name, unit in (contract.get("units") or {}).items():
        if not isinstance(actual.get("units"), Mapping) or actual["units"].get(name) != unit:
            errors.append(f"unit mismatch or missing: {name}")
    for name, value in (contract.get("scope") or {}).items():
        if not isinstance(actual.get("scope"), Mapping) or actual["scope"].get(name) != value:
            errors.append(f"scope mismatch or missing: {name}")
    if contract.get("time_range"):
        try:
            start, end = actual["time_range"]["start"], actual["time_range"]["end"]
            if _date(start) > _date(contract["time_range"]["start"]) or _date(end) < _date(contract["time_range"]["end"]):
                errors.append("time range does not cover required interval")
        except (KeyError, TypeError, ValueError):
            errors.append("time range metadata missing or invalid")
    return errors


def check_resource_contracts(contracts: list[Mapping[str, Any]], handles: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    violations = []
    for contract in contracts:
        source = contract.get("source_task_id")
        candidates = []
        for handle in handles:
            origin = (handle.get("metadata") or {}).get("workflow_origin", {})
            sources = {handle.get("source_task_id"), origin.get("source_task_id"), *(origin.get("source_task_ids") or [])}
            if source is None or source in sources:
                candidates.append(handle)
        errors = [_check(contract, handle) for handle in candidates]
        if any(not error for error in errors):
            continue
        violations.append({"source_task_id": source, "code": "resource_incompatible" if candidates else "resource_missing",
                           "required": contract.get("required", True),
                           "details": errors or [["no matching upstream resource"]]})
    return violations


def assert_resource_contracts(contracts: list[Mapping[str, Any]], handles: list[Mapping[str, Any]]) -> None:
    violations = [item for item in check_resource_contracts(contracts, handles) if item["required"]]
    if violations:
        raise ResourceContractError(violations)
