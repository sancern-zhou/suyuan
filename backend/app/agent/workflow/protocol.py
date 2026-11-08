"""Optional structured results for parent/child agent workflows."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional

_FENCED_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*[\s\S]*?```", re.IGNORECASE)


def strip_embedded_json_blocks(text: Any) -> str:
    """去掉答案里内嵌的 ```json 结构化块。

    子 Agent 未交付 submit_result 时会把结构化 JSON 粘贴进最终答案；
    structured_result 已单独传递，摘要（envelope.summary / 父视图）里
    再带一遍是纯重复（实测单次工作流返回因此膨胀数十 KB）。
    """
    return _FENCED_JSON_BLOCK_RE.sub(" ", str(text or ""))

# The shared envelope is intentionally domain-neutral. A caller may define its
# own result_schema inside outputs without adopting a fixed task protocol.
AGENT_RESULT_ENVELOPE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["status", "summary", "outputs", "evidence", "uncertainties", "artifacts"],
    "properties": {
        "status": {"type": "string", "enum": ["completed", "completed_with_gaps", "needs_more_evidence", "failed", "cancelled"]},
        "summary": {"type": "string"},
        "outputs": {"type": "object"},
        "evidence": {"type": "array", "items": {"type": "object"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "artifacts": {"type": "array", "items": {"type": "object"}},
        "errors": {"type": "array", "items": {"type": "object"}},
        "metadata": {"type": "object"},
    },
    "additionalProperties": True,
}

def build_result_envelope(
    *,
    status: str,
    summary: str = "",
    outputs: Optional[Mapping[str, Any]] = None,
    evidence: Optional[Iterable[Mapping[str, Any]]] = None,
    uncertainties: Optional[Iterable[str]] = None,
    artifacts: Optional[Iterable[Mapping[str, Any]]] = None,
    errors: Optional[Iterable[Mapping[str, Any]]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a stable result envelope independent of any business mode."""
    return {
        "status": status,
        "summary": summary,
        "outputs": deepcopy(dict(outputs or {})),
        "evidence": [deepcopy(dict(item)) for item in (evidence or [])],
        "uncertainties": [str(item) for item in (uncertainties or [])],
        "artifacts": [deepcopy(dict(item)) for item in (artifacts or [])],
        "errors": [deepcopy(dict(item)) for item in (errors or [])],
        "metadata": deepcopy(dict(metadata or {})),
    }


def extract_structured_result(text: str) -> Optional[Any]:
    if not isinstance(text, str) or not text.strip():
        return None
    candidates: List[str] = [m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)]
    candidates.append(text.strip())
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                return value
            except json.JSONDecodeError:
                continue
    return None


def validate_result_schema(value: Any, schema: Mapping[str, Any]) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []

    def visit(node: Any, spec: Mapping[str, Any], path: str) -> None:
        expected_type = spec.get("type")
        if expected_type and not _matches_type(node, expected_type):
            violations.append({"path": path, "expected": str(expected_type), "got": _value_type(node)})
            return
        if "enum" in spec and node not in spec["enum"]:
            violations.append({"path": path, "expected": f"one of {spec['enum']}", "got": repr(node)})
        if isinstance(node, Mapping):
            for name in spec.get("required", []):
                if name not in node:
                    violations.append({"path": f"{path}.{name}", "expected": "required", "got": "missing"})
            for name, child_spec in spec.get("properties", {}).items():
                if name in node and isinstance(child_spec, Mapping):
                    visit(node[name], child_spec, f"{path}.{name}")
        elif isinstance(node, list) and isinstance(spec.get("items"), Mapping):
            for index, item in enumerate(node):
                visit(item, spec["items"], f"{path}[{index}]")

    visit(value, schema, "$")
    if schema.get("x-evidence-references") and isinstance(value, Mapping):
        evidence = value.get("evidence", [])
        evidence = evidence if isinstance(evidence, list) else []
        ids = set()
        for index, item in enumerate(evidence):
            if not isinstance(item, Mapping):
                continue
            evidence_id = item.get("id")
            if not isinstance(evidence_id, str) or not evidence_id.strip() or evidence_id in ids:
                violations.append({"path": f"$.evidence[{index}].id", "expected": "unique nonempty id", "got": str(evidence_id)})
            else:
                ids.add(evidence_id)
            for field in ("source", "locator"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    violations.append({"path": f"$.evidence[{index}].{field}", "expected": "nonempty source reference", "got": "missing"})
        findings = value.get("findings", [])
        for index, finding in enumerate(findings if isinstance(findings, list) else []):
            if not isinstance(finding, Mapping):
                continue
            refs = finding.get("evidence_ids")
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in ids for ref in refs):
                violations.append({"path": f"$.findings[{index}].evidence_ids", "expected": "nonempty references to evidence ids", "got": str(refs)})
    return violations


def _matches_type(value: Any, expected: Any) -> bool:
    expected_types = expected if isinstance(expected, list) else [expected]
    return any(
        (kind == "object" and isinstance(value, Mapping)) or
        (kind == "array" and isinstance(value, list)) or
        (kind == "string" and isinstance(value, str)) or
        (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or
        (kind == "integer" and isinstance(value, int) and not isinstance(value, bool)) or
        (kind == "boolean" and isinstance(value, bool)) or
        (kind == "null" and value is None)
        for kind in expected_types
    )


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__
