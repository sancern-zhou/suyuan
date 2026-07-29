from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ReportRefError(ValueError):
    """Raised when a report reference is missing or escapes its project."""


class PptReportStore:
    """Persist complete PPT reports and read exact issue evidence safely."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = (self.project_dir / ".editable-ppt" / "reports").resolve()

    def persist(self, operation: str, revision: int, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        target = self.reports_dir / f"{operation}-rev-{revision}-{digest}.json"
        if not target.exists():
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        return target.relative_to(self.project_dir).as_posix()

    def read(
        self,
        report_ref: str,
        *,
        pages: list[int] | None = None,
        codes: list[str] | None = None,
        element_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve(report_ref)
        payload = json.loads(target.read_text(encoding="utf-8"))
        if pages is None and codes is None and element_ids is None:
            return payload

        matched = [
            issue
            for issue in self._collect_issue_dicts(payload)
            if (pages is None or self._page(issue) in pages)
            and (codes is None or self._code(issue) in codes)
            and (element_ids is None or self._element_id(issue) in element_ids)
        ]
        report = payload.get("report", {}) if isinstance(payload, dict) else {}
        return {
            "report_ref": report_ref,
            "report_metadata": {
                "success": payload.get("success") if isinstance(payload, dict) else None,
                "slideCount": report.get("slideCount") if isinstance(report, dict) else None,
            },
            "matched_issues": matched,
        }

    def _resolve(self, report_ref: str) -> Path:
        candidate = (self.project_dir / report_ref).resolve()
        try:
            candidate.relative_to(self.reports_dir)
        except ValueError as exc:
            raise ReportRefError(
                "report_ref must stay inside the project reports directory"
            ) from exc
        if candidate.parent != self.reports_dir:
            raise ReportRefError(
                "report_ref must identify a file in the project reports directory"
            )
        if not candidate.is_file():
            raise ReportRefError("report does not exist in the project reports directory")
        return candidate

    @classmethod
    def _collect_issue_dicts(cls, value: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []

        def visit(node: Any):
            if isinstance(node, dict):
                for key, child in node.items():
                    if key == "issues" and isinstance(child, list):
                        found.extend(item for item in child if isinstance(item, dict))
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(value)
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for issue in found:
            identity = json.dumps(issue, ensure_ascii=False, sort_keys=True, default=str)
            if identity not in seen:
                seen.add(identity)
                unique.append(issue)
        return unique

    @staticmethod
    def _first(issue: dict[str, Any], *keys: str):
        return next((issue[key] for key in keys if issue.get(key) is not None), None)

    @classmethod
    def _page(cls, issue: dict[str, Any]):
        return cls._first(issue, "page", "pageNumber", "slideNumber")

    @classmethod
    def _code(cls, issue: dict[str, Any]):
        value = cls._first(issue, "code", "type", "kind")
        return str(value) if value is not None else None

    @classmethod
    def _element_id(cls, issue: dict[str, Any]):
        value = cls._first(issue, "element_id", "elementId", "sourceId", "id")
        return str(value) if value is not None else None
