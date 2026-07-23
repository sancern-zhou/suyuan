from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LIKELY_CAUSES = {
    "ELEMENT_OVERFLOW": "嵌套绝对定位或元素尺寸造成页面越界",
}


class PptDiagnosticBuilder:
    """Convert complete PPT reports into lossless, actionable diagnostics."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self.slides, self.sources_by_id = self._load_deck()

    def build(
        self,
        operation: str,
        raw: dict[str, Any],
        report_ref: str,
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        issues = [self._normalize(issue, report_ref) for issue in self._collect_issues(raw)]
        issues.sort(key=self._issue_sort_key)
        fingerprint = self._fingerprint(operation, issues) if issues else None
        previous_fingerprint = previous.get("fingerprint") if isinstance(previous, dict) else None
        if not fingerprint and previous_fingerprint:
            status = "resolved"
        elif previous is None:
            status = "new"
        elif fingerprint and fingerprint == previous_fingerprint:
            status = "unchanged"
        elif fingerprint != previous_fingerprint:
            status = "changed"
        else:
            status = "new"
        return {
            "fingerprint": fingerprint,
            "status": status,
            "issue_count": len(issues),
            "groups": self._groups(issues),
            "issues": issues,
        }

    def recommended_action(self, diagnostic: dict[str, Any]) -> dict[str, Any]:
        source_paths: list[str] = []
        for issue in diagnostic.get("issues", []):
            source_path = issue.get("source_path")
            if source_path and source_path not in source_paths:
                source_paths.append(source_path)
        return {
            "action": "read_sources" if diagnostic.get("issue_count") else "continue_quality_flow",
            "source_paths": source_paths,
        }

    def _load_deck(self) -> tuple[list[tuple[str | None, str | None]], dict[str, str]]:
        try:
            deck = json.loads((self.project_dir / "deck.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return [], {}
        slides: list[tuple[str | None, str | None]] = []
        sources_by_id: dict[str, str] = {}
        for index, item in enumerate(deck.get("slides", []), start=1):
            if isinstance(item, str):
                slide_id = item
                source = f"slides/slide-{index:03d}.js"
            elif isinstance(item, dict):
                slide_id = item.get("id")
                source = item.get("source") or item.get("source_path") or item.get("sourcePath")
                source = source or f"slides/slide-{index:03d}.js"
            else:
                slide_id = None
                source = None
            slides.append((slide_id, source))
            if slide_id and source:
                sources_by_id[str(slide_id)] = str(source)
        return slides, sources_by_id

    @classmethod
    def _collect_issues(cls, value: Any) -> list[dict[str, Any]]:
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

    def _normalize(self, raw_issue: dict[str, Any], report_ref: str) -> dict[str, Any]:
        page = self._first(raw_issue, "page", "pageNumber", "slideNumber")
        slide_id = self._first(raw_issue, "slide_id", "slideId")
        element_id = self._first(raw_issue, "element_id", "elementId", "sourceId")
        code = self._first(raw_issue, "code", "type", "kind") or "UNKNOWN_PPT_ISSUE"
        source_path = self._source_path(raw_issue, slide_id, page)
        normalized = {
            "page": page,
            "slide_id": slide_id,
            "element_id": element_id,
            "code": str(code),
            "message": self._first(raw_issue, "message", "description") or "未分类 PPT 诊断",
            "severity": raw_issue.get("severity") or "error",
            "source_path": source_path,
            "measured_box": self._first(raw_issue, "measured_box", "box", "bounds"),
            "expected_bounds": self._first(raw_issue, "expected_bounds", "viewport"),
            "evidence_ref": {"report_ref": report_ref},
            "raw_issue": raw_issue,
        }
        for key in ("expected", "actual", "property", "location"):
            if key in raw_issue:
                normalized[key] = raw_issue[key]
        return normalized

    def _source_path(self, issue: dict[str, Any], slide_id: Any, page: Any) -> str | None:
        explicit = self._first(issue, "source_path", "sourcePath", "relative_path")
        if explicit:
            return str(explicit)
        if str(issue.get("code") or "") == "REQUESTED_PAGE_COUNT_MISMATCH":
            return "deck.json"
        if slide_id is not None and str(slide_id) in self.sources_by_id:
            return self.sources_by_id[str(slide_id)]
        if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= len(self.slides):
            return self.slides[page - 1][1]
        return None

    @staticmethod
    def _issue_sort_key(issue: dict[str, Any]):
        page = issue.get("page")
        return (
            page if isinstance(page, int) else 10**9,
            str(issue.get("code") or ""),
            str(issue.get("element_id") or ""),
        )

    @staticmethod
    def _groups(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for issue in issues:
            grouped.setdefault(issue["code"], []).append(issue)
        result = []
        for code in sorted(grouped):
            members = grouped[code]
            pages = sorted({item["page"] for item in members if isinstance(item.get("page"), int)})
            group = {"code": code, "count": len(members), "pages": pages}
            if code in LIKELY_CAUSES:
                group["likely_cause"] = LIKELY_CAUSES[code]
            result.append(group)
        return result

    @staticmethod
    def _fingerprint(operation: str, issues: list[dict[str, Any]]) -> str:
        identities = []
        for issue in issues:
            raw = issue.get("raw_issue") or {}
            location = issue.get("location") or raw.get("property") or raw.get("path")
            identities.append(
                (
                    operation,
                    issue.get("code"),
                    issue.get("slide_id"),
                    issue.get("page"),
                    issue.get("element_id"),
                    location,
                )
            )
        serialized = json.dumps(
            sorted(identities, key=lambda item: tuple("" if value is None else str(value) for value in item)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
