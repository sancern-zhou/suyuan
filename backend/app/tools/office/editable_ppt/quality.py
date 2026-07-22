from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EditablePptGate:
    status: str
    blocking: bool
    issues: list[dict[str, Any]]

    def to_dict(self):
        return {"status": self.status, "blocking": self.blocking, "issues": self.issues}


BLOCKING_CODES = {
    "FORBIDDEN_RASTER_FALLBACK", "NATIVE_REFERENCE_MISSING", "OOXML_STRUCTURE_INVALID",
    "CRITICAL_ELEMENT_MISSING", "CRITICAL_ELEMENT_GEOMETRY_DRIFT", "BLANK_SLIDE",
    "MISSING_ASSET", "POWERPOINT_REPAIR_RISK",
}


def _issue(code, message, severity="error", **extra):
    return {"code": code, "severity": severity, "message": message, **extra}


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    code = item.get("code") or str(item.get("type", "QA_ISSUE")).upper()
    return {
        "code": code,
        "slide_id": item.get("slide_id") or item.get("slideId"),
        "element_id": item.get("element_id") or item.get("elementId"),
        "severity": item.get("severity", "error"),
        "message": item.get("message", code),
        "evidence": item.get("evidence"),
        "suggestion": item.get("suggestion"),
    }


def build_editable_ppt_gate(
    compile_report: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    visual_comparison: dict[str, Any] | None = None,
) -> EditablePptGate:
    issues = []
    compile_report = compile_report or {}
    validation = validation or {}
    forbidden = int(compile_report.get("forbiddenRasterFallbacks", 0) or 0)
    if forbidden:
        issues.append(_issue(
            "FORBIDDEN_RASTER_FALLBACK",
            f"strict 模式检测到 {forbidden} 个禁止的栅格回退",
            evidence={"count": forbidden, "element_ids": compile_report.get("forbiddenElementIds", [])},
            suggestion="将文字、图表或表格改为原生 PPTX 对象",
        ))
    issues.extend(_normalize(item) for item in compile_report.get("issues", []))
    issues.extend(_normalize(item) for item in validation.get("issues", []))
    issues.extend(_normalize(item) for item in (visual_comparison or {}).get("issues", []))
    validation_passed = validation.get("success") is True or validation.get("gate", {}).get("passed") is True
    if not validation and compile_report:
        issues.append(_issue("PPTX_QA_UNAVAILABLE", "尚未执行 PPTX 渲染验证", severity="warning"))
    blocking = any(item["code"] in BLOCKING_CODES or item.get("severity") == "error" for item in issues)
    if blocking:
        status = "needs_revision"
    elif not validation_passed:
        status = "qa_failed"
        blocking = True
    else:
        status = "passed"
    return EditablePptGate(status, blocking, issues)
