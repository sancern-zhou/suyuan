from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisualComparison:
    issues: list[dict[str, Any]]
    page_difference_score: float | None = None

    def to_dict(self):
        return {"issues": self.issues, "page_difference_score": self.page_difference_score}


def _box(value):
    if isinstance(value, dict):
        return [value.get("x", 0), value.get("y", 0), value.get("width", 0), value.get("height", 0)]
    return list(value)


def compare_slide_renders(
    html_png, pptx_png, html_elements, pptx_elements, geometry_tolerance_px=4,
) -> VisualComparison:
    del html_png, pptx_png  # Pixel difference is optional; stable-ID geometry is the delivery gate.
    actual = {item["id"]: item for item in pptx_elements}
    issues = []
    for expected in html_elements:
        if not expected.get("critical", False):
            continue
        item = actual.get(expected["id"])
        if item is None:
            issues.append({
                "code": "CRITICAL_ELEMENT_MISSING", "severity": "error",
                "element_id": expected["id"], "message": "关键元素未出现在 PPTX 渲染中",
                "evidence": {"expected_box": _box(expected["box"])},
            })
            continue
        expected_box, actual_box = _box(expected["box"]), _box(item["box"])
        drift = max(abs(a - b) for a, b in zip(expected_box, actual_box))
        if drift > geometry_tolerance_px:
            issues.append({
                "code": "CRITICAL_ELEMENT_GEOMETRY_DRIFT", "severity": "error",
                "element_id": expected["id"], "message": f"关键元素几何偏移 {drift}px",
                "evidence": {"expected_box": expected_box, "actual_box": actual_box, "tolerance_px": geometry_tolerance_px},
            })
    return VisualComparison(issues)
