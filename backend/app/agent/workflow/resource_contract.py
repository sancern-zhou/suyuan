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

# 交付链路当前没有 metadata.data_contract 的生产写入通道（全仓只有测试构造过），
# 声明这些约束在交接校验时永远无法满足——解析期直接拒绝，编排模型当场改稿，
# 不让必死的契约进入运行期。引入资源元数据写入能力后，把对应键移出本元组即可解锁。
_CONSTRAINTS_WITHOUT_PRODUCER = ("granularity", "time_range", "units", "scope")
# kind 的取值域；format 必须是具体文件格式（可从交付文件后缀核对），"file"/"data" 是 kind 的语义。
_KIND_VALUES = ("file", "data")
_KIND_SEMANTIC_VALUES = ("file", "data")


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
    declared_unproducible = [key for key in _CONSTRAINTS_WITHOUT_PRODUCER if key in contract]
    if declared_unproducible:
        raise ValueError(
            "resource contract 不可声明 " + "/".join(declared_unproducible)
            + "：交付链路没有这些元数据的写入通道，交接校验必然失败；"
            "口径请写进节点 goal 与 result_schema 字段描述（模型可读），"
            "文件类要求用 result_schema 的 deliverables 数组承载"
        )
    if contract.get("format") in _KIND_SEMANTIC_VALUES:
        raise ValueError(
            f"resource contract format 不能是 '{contract['format']}'（这是 kind 的语义）："
            "format 必须是具体文件格式（csv/json/xlsx/qmd 等），交接时按交付文件后缀核对"
        )
    if "kind" in contract and contract["kind"] not in _KIND_VALUES:
        raise ValueError(
            f"resource contract kind 必须是 {'/'.join(_KIND_VALUES)} 之一，got '{contract['kind']}'"
        )
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


def _json_type(value: Any) -> str:
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def validate_deliverable_entries(entries: Any) -> list[dict[str, str]]:
    """核验交付信封的 deliverables 数组：交货方自报路径 → 机械核对真实文件。

    每项要求 path 指向真实存在的文件；声明 format 时与文件后缀一致；
    声明 fields 时按形态分级核验（2026-11-05 降档）：csv 核对表头、能解析出
    records/rows/data 记录列表的 json 核对键交集，二者为硬性；顶层结构键的
    嵌套 JSON（报表包）与不可核对格式（图片、超大 JSON 等）视为信息性声明，
    不再判死——此类核验不可靠且子 Agent 无从修复（qingyuan-oct DAG 失败教训）。
    返回 validate_result_schema 同形的违规列表（path/expected/got），空列表即
    通过；调用方把违规并进结构化交付的校验错误，由既有修复轮喂回原子会话修正。
    """
    if entries is None:
        return []
    if not isinstance(entries, list):
        return [{"path": "$.deliverables", "expected": "array of {path, format?, fields?}", "got": _json_type(entries)}]
    violations: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        prefix = f"$.deliverables[{index}]"
        if not isinstance(entry, Mapping):
            violations.append({"path": prefix, "expected": "object with path", "got": _json_type(entry)})
            continue
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            violations.append({"path": f"{prefix}.path", "expected": "nonempty file path", "got": "missing"})
            continue
        path_prefix = f"{prefix}.path"
        try:
            path = resolve_agent_path(raw_path)
        except (OSError, ValueError, TypeError) as exc:
            violations.append({"path": path_prefix, "expected": "resolvable file path", "got": str(exc)})
            continue
        if not path.is_file():
            violations.append({"path": path_prefix, "expected": "existing file", "got": "not found"})
            continue
        declared_format = entry.get("format")
        if isinstance(declared_format, str) and declared_format:
            actual_format = path.suffix.lower().lstrip(".")
            if actual_format != declared_format.lower():
                violations.append({"path": f"{prefix}.format", "expected": declared_format, "got": actual_format or "none"})
        declared_fields = entry.get("fields")
        if isinstance(declared_fields, list) and declared_fields and all(isinstance(f, str) for f in declared_fields):
            suffix = path.suffix.lower()
            verifiable = suffix == ".csv" or (
                suffix == ".json" and path.stat().st_size <= 2 * 1024 * 1024
            )
            if not verifiable:
                # 不可核对格式（图片、超大 JSON 等）：fields 视为信息性声明，不判死
                continue
            try:
                if suffix == ".csv":
                    actual_fields = _file_fields(path)
                    records_shaped = True
                else:
                    actual_fields, records_shaped = _json_record_fields(path)
            except (OSError, ValueError, TypeError) as exc:
                violations.append({"path": f"{prefix}.fields", "expected": "inspectable file", "got": str(exc)})
                continue
            # 仅顶层结构键的嵌套 JSON（报表包）：键集合不代表记录字段，fields 不判死
            if records_shaped:
                missing = sorted(set(declared_fields) - (actual_fields or set()))
                if missing:
                    violations.append({"path": f"{prefix}.fields", "expected": declared_fields, "got": f"missing {missing}"})
    return violations


def _file_fields(path: Path) -> set[str] | None:
    """Bounded inspection; large JSON requires explicit catalog schema metadata."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = stream.readline(65537)
        if len(header) > 65536:
            raise ValueError("CSV header exceeds inspection limit")
        return set(next(csv.reader([header]), []))
    if path.suffix.lower() == ".json" and path.stat().st_size <= 2 * 1024 * 1024:
        fields, _descended = _json_record_fields(path)
        return fields
    return None


def _json_record_fields(path: Path) -> tuple[set[str] | None, bool]:
    """小型 JSON 的字段核验信息：返回 (键集合, 是否解析自 records/rows/data 记录列表)。

    descended=True 表示键集合来自记录列表的行键交集（可靠，可作硬核验依据）；
    False 表示只拿到顶层结构键（报表包等嵌套结构的 structural keys 不代表
    记录字段，据此核对必然误报 missing）。
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    descended = False
    for _ in range(4):
        if not isinstance(value, Mapping):
            break
        nested = next((value[key] for key in ("records", "rows", "data") if isinstance(value.get(key), (list, dict))), None)
        if nested is None:
            break
        descended = True
        value = nested
    if isinstance(value, list):
        fields = None
        for row in value:
            if not isinstance(row, Mapping):
                return set(), descended
            fields = set(row) if fields is None else fields.intersection(row)
        return (fields or set()), descended
    if isinstance(value, Mapping):
        return set(value), descended
    return None, descended


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


def fatal_resource_contract_violations(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """资源契约违规中仍应判节点失败的子集（2026-11-05 语义收窄）。

    仅 required 上游资源整体缺失（resource_missing，下游在没有任何可消费
    产物时运行纯属浪费）保持 fatal；形态不符（resource_incompatible，
    format/fields 与契约不一致）只记录不判死——契约已注入子 Agent 指令、
    违规随 node_contract_errors 与 delivery.gaps 暴露给父侧整合，子代理
    交付 json 而契约写 csv 不应废掉整节点（qingyuan-oct qy-weather/qy-station
    两节点教训）。
    """
    return [
        item for item in violations
        if item.get("required", True) and item.get("code") == "resource_missing"
    ]
