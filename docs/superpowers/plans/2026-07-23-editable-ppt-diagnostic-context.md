# Editable PPT Diagnostic Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `manage_editable_ppt` preserve complete PPT reports on disk while returning accurate, compact, source-addressable diagnostics that guide the PPT Agent through a reliable read-source-before-edit workflow.

**Architecture:** Add two focused PPT-only units: `PptReportStore` owns safe, immutable report persistence and filtered reads; `PptDiagnosticBuilder` normalizes all actionable issues, maps them to slide sources, computes stable fingerprints, and compares the previous diagnostic. `ManageEditablePptTool` keeps raw results for internal compile/finalize gates but exposes only a diagnostic envelope to the Agent, plus a guarded `read_report` operation. No generic Agent runtime or context builder changes are included.

**Tech Stack:** Python 3.11, pytest/pytest-asyncio, existing editable PPT Python tool, existing Node.js compiler CLI, JSON report artifacts, Markdown prompt/reference tests.

---

## File map

- Create `backend/app/tools/office/editable_ppt/report_store.py`: immutable report filenames, safe `report_ref` resolution, complete and filtered report reads.
- Create `backend/app/tools/office/editable_ppt/diagnostics.py`: issue normalization, source mapping, grouping, stable fingerprints, status comparison, envelope construction.
- Modify `backend/app/tools/office/editable_ppt/tool.py`: add `read_report`; persist raw render/compile/validate results; return diagnostic envelopes; keep raw internal validation for finalize.
- Modify `backend/app/tools/office/editable_ppt/__init__.py`: export the new focused classes.
- Create `backend/tests/tools/office/editable_ppt/test_report_store.py`: persistence, filtering, and path-safety tests.
- Create `backend/tests/tools/office/editable_ppt/test_diagnostics.py`: exhaustive issue extraction, source mapping, grouping, fingerprint, and transition tests.
- Modify `backend/tests/tools/office/editable_ppt/test_tool.py`: schema and tool-level compact-result tests.
- Modify `backend/tests/tools/office/editable_ppt/test_e2e.py`: real compiler regression proving compact responses preserve compile/finalize behavior.
- Modify `backend/app/tools/office/editable_ppt/references/workflow.md`: replace advisory prose with the approved stage protocol.
- Modify `backend/app/agent/prompts/ppt_prompt.py`: add the read-diagnostic → read-source → batch-edit behavior rules.
- Modify `backend/app/agent/prompts/ppt_mode_spec.py`: lock the new prompt contract.

### Task 1: Safe immutable PPT report storage

**Files:**
- Create: `backend/app/tools/office/editable_ppt/report_store.py`
- Create: `backend/tests/tools/office/editable_ppt/test_report_store.py`
- Modify: `backend/app/tools/office/editable_ppt/__init__.py`

- [ ] **Step 1: Write failing persistence and filtering tests**

Create `backend/tests/tools/office/editable_ppt/test_report_store.py` with these cases:

```python
import json
from pathlib import Path

import pytest

from app.tools.office.editable_ppt.report_store import PptReportStore, ReportRefError


def sample_report():
    return {
        "success": False,
        "report": {
            "slideCount": 4,
            "issues": [
                {"code": "ELEMENT_OVERFLOW", "page": 3, "elementId": "chart-a", "message": "overflow"},
                {"code": "DUPLICATE_ID", "page": 4, "elementId": "title", "message": "duplicate"},
            ],
            "measurement": {"screenshots": ["a.png", "b.png"]},
        },
    }


def test_persist_keeps_complete_payload_and_returns_project_relative_ref(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)

    report_ref = store.persist("compile", revision=7, payload=sample_report())

    assert report_ref.startswith(".editable-ppt/reports/compile-rev-7-")
    assert report_ref.endswith(".json")
    assert store.read(report_ref) == sample_report()
    assert json.loads((project / report_ref).read_text(encoding="utf-8")) == sample_report()


def test_persist_is_content_addressed_and_does_not_overwrite_other_payload(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)

    first = store.persist("render", 2, {"pages": [{"page": 1}]})
    second = store.persist("render", 2, {"pages": [{"page": 2}]})

    assert first != second
    assert store.read(first)["pages"][0]["page"] == 1
    assert store.read(second)["pages"][0]["page"] == 2


def test_read_filters_issue_nodes_without_losing_matched_raw_fields(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)
    ref = store.persist("compile", 7, sample_report())

    filtered = store.read(ref, pages=[3], codes=["ELEMENT_OVERFLOW"], element_ids=["chart-a"])

    assert filtered["report_ref"] == ref
    assert filtered["matched_issues"] == [sample_report()["report"]["issues"][0]]
    assert filtered["report_metadata"]["success"] is False
    assert filtered["report_metadata"]["slideCount"] == 4


@pytest.mark.parametrize("report_ref", [
    "../secret.json",
    ".editable-ppt/reports/../../secret.json",
    "/tmp/secret.json",
    ".editable-ppt/last_compile.json",
])
def test_read_rejects_refs_outside_reports_directory(tmp_path, report_ref):
    project = tmp_path / "deck"
    project.mkdir()

    with pytest.raises(ReportRefError, match="reports directory"):
        PptReportStore(project).read(report_ref)
```

- [ ] **Step 2: Run the new tests and verify the module is missing**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/office/editable_ppt/test_report_store.py
```

Expected: collection fails with `ModuleNotFoundError: ...report_store`.

- [ ] **Step 3: Implement the report store**

Create `backend/app/tools/office/editable_ppt/report_store.py` with:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ReportRefError(ValueError):
    pass


class PptReportStore:
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = (self.project_dir / ".editable-ppt" / "reports").resolve()

    def persist(self, operation: str, revision: int, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
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
        issues = self._collect_issue_dicts(payload)
        matched = [
            issue for issue in issues
            if (pages is None or self._page(issue) in pages)
            and (codes is None or str(issue.get("code") or issue.get("type")) in codes)
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
            raise ReportRefError("report_ref must stay inside the project reports directory") from exc
        if candidate.parent != self.reports_dir or not candidate.is_file():
            raise ReportRefError("report_ref must identify a report in the project reports directory")
        return candidate
```

Complete `_collect_issue_dicts`, `_page`, and `_element_id` as small deterministic helpers. `_collect_issue_dicts` must recursively find dictionaries contained in a list whose parent key is `issues`, preserve each dictionary unchanged, and deduplicate equal nodes by canonical JSON. `_page` must accept `page`, `pageNumber`, and `slideNumber`; `_element_id` must accept `element_id`, `elementId`, `sourceId`, and `id`.

Export `PptReportStore` and `ReportRefError` from `backend/app/tools/office/editable_ppt/__init__.py`.

- [ ] **Step 4: Run the report-store tests**

Run the command from Step 2.

Expected: all tests in `test_report_store.py` pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/tools/office/editable_ppt/report_store.py backend/app/tools/office/editable_ppt/__init__.py backend/tests/tools/office/editable_ppt/test_report_store.py
git commit -m "feat: persist editable PPT reports safely"
```

### Task 2: Lossless actionable diagnostic builder

**Files:**
- Create: `backend/app/tools/office/editable_ppt/diagnostics.py`
- Create: `backend/tests/tools/office/editable_ppt/test_diagnostics.py`
- Modify: `backend/app/tools/office/editable_ppt/__init__.py`

- [ ] **Step 1: Write failing normalization and fingerprint tests**

Create `backend/tests/tools/office/editable_ppt/test_diagnostics.py`. Use a temporary project containing this `deck.json`:

```python
DECK = {
    "slides": [
        {"id": "cover", "source": "slides/slide-001.js"},
        {"id": "air-chart", "source": "slides/slide-002.js"},
        {"id": "station-chart", "source": "slides/slide-003.js"},
    ]
}
```

Add tests with these exact assertions:

```python
def test_build_keeps_every_issue_and_maps_sources(project_dir):
    raw = {
        "success": False,
        "error": "SLIDE_MEASUREMENT_GATE_FAILED",
        "report": {
            "slideCount": 3,
            "issues": [
                {
                    "code": "ELEMENT_OVERFLOW",
                    "page": 2,
                    "slideId": "air-chart",
                    "sourceId": "pollutant-bar-chart",
                    "message": "outside viewport",
                    "box": {"x": 200, "y": 280, "width": 1240, "height": 600},
                },
                {
                    "code": "ELEMENT_OVERFLOW",
                    "page": 3,
                    "slideId": "station-chart",
                    "sourceId": "station-bar-chart",
                    "message": "outside viewport",
                    "box": {"x": 200, "y": 280, "width": 1240, "height": 600},
                },
            ],
        },
    }

    diagnostic = PptDiagnosticBuilder(project_dir).build(
        operation="compile", raw=raw, report_ref=".editable-ppt/reports/r.json", previous=None
    )

    assert diagnostic["issue_count"] == 2
    assert [item["source_path"] for item in diagnostic["issues"]] == [
        "slides/slide-002.js", "slides/slide-003.js"
    ]
    assert diagnostic["groups"] == [{
        "code": "ELEMENT_OVERFLOW",
        "count": 2,
        "pages": [2, 3],
        "likely_cause": "嵌套绝对定位或元素尺寸造成页面越界",
    }]


def test_unknown_issue_shape_is_preserved_as_generic_diagnostic(project_dir):
    raw_issue = {"kind": "new_compiler_problem", "details": {"path": "x.y"}, "message": "new"}
    diagnostic = PptDiagnosticBuilder(project_dir).build(
        operation="render",
        raw={"success": False, "issues": [raw_issue]},
        report_ref=".editable-ppt/reports/r.json",
        previous=None,
    )

    assert diagnostic["issue_count"] == 1
    assert diagnostic["issues"][0]["raw_issue"] == raw_issue
    assert diagnostic["issues"][0]["code"] == "UNKNOWN_PPT_ISSUE"


def test_fingerprint_ignores_order_report_ref_timing_and_revision(project_dir):
    first = make_two_issue_result(order="forward", duration=100)
    second = make_two_issue_result(order="reverse", duration=900)
    builder = PptDiagnosticBuilder(project_dir)

    d1 = builder.build("compile", first, ".editable-ppt/reports/one.json", previous=None)
    d2 = builder.build("compile", second, ".editable-ppt/reports/two.json", previous=d1)

    assert d1["fingerprint"] == d2["fingerprint"]
    assert d2["status"] == "unchanged"


def test_status_transitions_cover_new_changed_unchanged_and_resolved(project_dir):
    builder = PptDiagnosticBuilder(project_dir)
    first = builder.build("compile", one_issue("a"), "r1.json", previous=None)
    changed = builder.build("compile", one_issue("b"), "r2.json", previous=first)
    unchanged = builder.build("compile", one_issue("b"), "r3.json", previous=changed)
    resolved = builder.build("compile", {"success": True, "report": {"issues": []}}, "r4.json", previous=unchanged)

    assert [first["status"], changed["status"], unchanged["status"], resolved["status"]] == [
        "new", "changed", "unchanged", "resolved"
    ]
```

Also test page-count mismatch normalization using an explicit synthetic issue passed by the tool integration later: `REQUESTED_PAGE_COUNT_MISMATCH` must map to `deck.json`, not a slide source.

- [ ] **Step 2: Run diagnostics tests and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/office/editable_ppt/test_diagnostics.py
```

Expected: collection fails because `diagnostics.py` does not exist.

- [ ] **Step 3: Implement diagnostic normalization**

Create `backend/app/tools/office/editable_ppt/diagnostics.py` with these public contracts:

```python
class PptDiagnosticBuilder:
    def __init__(self, project_dir: str | Path): ...

    def build(
        self,
        operation: str,
        raw: dict[str, Any],
        report_ref: str,
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    def recommended_action(self, diagnostic: dict[str, Any]) -> dict[str, Any]: ...
```

Implementation rules:

1. Recursively collect every dictionary inside lists named `issues`; include top-level compiler exceptions converted by the tool as issue dictionaries.
2. Deduplicate only byte-equivalent canonical issue dictionaries, not merely equal codes.
3. Normalize aliases without discarding the original node:

```python
normalized = {
    "page": first(raw_issue, "page", "pageNumber", "slideNumber"),
    "slide_id": first(raw_issue, "slide_id", "slideId"),
    "element_id": first(raw_issue, "element_id", "elementId", "sourceId"),
    "code": first(raw_issue, "code", "type", "kind") or "UNKNOWN_PPT_ISSUE",
    "message": first(raw_issue, "message", "description") or "未分类 PPT 诊断",
    "severity": raw_issue.get("severity") or "error",
    "source_path": mapped_source,
    "measured_box": first(raw_issue, "measured_box", "box", "bounds"),
    "expected_bounds": first(raw_issue, "expected_bounds", "viewport"),
    "evidence_ref": {"report_ref": report_ref},
    "raw_issue": raw_issue,
}
```

4. Load `deck.json` defensively. Map by explicit source path first, then stable slide ID, then one-based page index. Project-level issues map to `deck.json`. Unknown mappings remain `None`; never invent a filename.
5. Group by normalized code, preserving sorted unique pages. A deterministic rule table may provide `likely_cause`; only `ELEMENT_OVERFLOW` initially maps to `嵌套绝对定位或元素尺寸造成页面越界`.
6. Compute the fingerprint from sorted tuples of `operation`, `code`, `slide_id`, `page`, `element_id`, and a normalized location/property. Do not include message wording, raw ordering, timing, revision, or report path.
7. A zero-issue success has fingerprint `None`. Status is `resolved` only when a previous nonempty fingerprint becomes empty; otherwise the first observation is `new`, equal nonempty fingerprints are `unchanged`, and different fingerprints are `changed`.
8. `recommended_action` returns unique non-null `source_paths`. With issues it returns `{"action": "read_sources", ...}`; without issues it returns `{"action": "continue_quality_flow", "source_paths": []}`.

Export `PptDiagnosticBuilder` from `backend/app/tools/office/editable_ppt/__init__.py`.

- [ ] **Step 4: Run diagnostics tests**

Run the command from Step 2.

Expected: all diagnostics tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/tools/office/editable_ppt/diagnostics.py backend/app/tools/office/editable_ppt/__init__.py backend/tests/tools/office/editable_ppt/test_diagnostics.py
git commit -m "feat: build actionable PPT diagnostics"
```

### Task 3: Integrate compact diagnostic envelopes into the PPT tool

**Files:**
- Modify: `backend/app/tools/office/editable_ppt/tool.py`
- Modify: `backend/tests/tools/office/editable_ppt/test_tool.py`

- [ ] **Step 1: Extend the tool tests with failing schema and response assertions**

Update `test_schema_exposes_complete_direct_document_edit_contract` so the expected operation set also contains `read_report`, and assert that branch requires `operation`, `project_dir`, and `report_ref`, with optional arrays `pages`, `codes`, and `element_ids`.

Add a failing compiler fixture and tests:

```python
class DiagnosticCompiler(FakeCompiler):
    async def preview(self, project_dir, output_dir=None, **kwargs):
        huge_tree = {"nodes": [f"node-{index}" for index in range(5000)]}
        return {
            "success": False,
            "pages": huge_tree,
            "issues": [{
                "code": "ELEMENT_OVERFLOW", "page": 1, "slideId": "cover",
                "sourceId": "hero", "message": "outside viewport",
                "box": {"x": 0, "y": 760, "width": 1440, "height": 100},
            }],
        }

    async def compile(self, project_dir, output_dir=None, **kwargs):
        return {
            "success": False,
            "error": "SLIDE_MEASUREMENT_GATE_FAILED",
            "report": {
                "slideCount": 1,
                "issues": [{
                    "code": "ELEMENT_OVERFLOW", "page": 1, "slideId": "cover",
                    "sourceId": "hero", "message": "outside viewport",
                }],
                "measurement": {"domTree": "x" * 80000},
            },
        }


@pytest.mark.asyncio
async def test_render_persists_raw_result_but_returns_compact_complete_diagnostic(tmp_path):
    tool = ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path),
        compiler_client=DiagnosticCompiler(),
    )
    created = await tool.execute(operation="create", title="诊断")

    result = await tool.execute(operation="render", project_dir=created["data"]["project_dir"])

    assert result["success"] is False
    assert result["data"]["diagnostic"]["issue_count"] == 1
    assert result["data"]["diagnostic"]["issues"][0]["source_path"] == "slides/slide-001.js"
    assert "nodes" not in result["data"]
    assert len(json.dumps(result, ensure_ascii=False)) < 10_000
    raw = json.loads(Path(created["data"]["project_dir"], result["data"]["report_ref"]).read_text())
    assert len(raw["pages"]["nodes"]) == 5000


@pytest.mark.asyncio
async def test_compile_reports_unchanged_after_ineffective_edit_cycle(tmp_path):
    tool = ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path),
        compiler_client=DiagnosticCompiler(),
    )
    created = await tool.execute(operation="create", title="诊断")
    first = await tool.execute(operation="compile", project_dir=created["data"]["project_dir"])
    second = await tool.execute(operation="compile", project_dir=created["data"]["project_dir"])

    assert first["data"]["diagnostic"]["status"] == "new"
    assert second["data"]["diagnostic"]["status"] == "unchanged"
    assert second["data"]["recommended_action"]["source_paths"] == ["slides/slide-001.js"]


@pytest.mark.asyncio
async def test_read_report_returns_filtered_raw_evidence(tmp_path):
    tool = ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path),
        compiler_client=DiagnosticCompiler(),
    )
    created = await tool.execute(operation="create", title="诊断")
    compiled = await tool.execute(operation="compile", project_dir=created["data"]["project_dir"])

    evidence = await tool.execute(
        operation="read_report",
        project_dir=created["data"]["project_dir"],
        report_ref=compiled["data"]["report_ref"],
        pages=[1],
        codes=["ELEMENT_OVERFLOW"],
        element_ids=["hero"],
    )

    assert evidence["success"] is True
    assert evidence["data"]["report"]["matched_issues"][0]["sourceId"] == "hero"
```

- [ ] **Step 2: Run focused tool tests and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/office/editable_ppt/test_tool.py
```

Expected: failures for the missing `read_report` operation and raw oversized render/compile payloads.

- [ ] **Step 3: Add the `read_report` schema branch and dependencies**

In `ManageEditablePptTool.__init__`, add:

```python
_branch("read_report", ["project_dir", "report_ref"], {
    **PROJECT,
    "report_ref": {"type": "string"},
    "pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
    "codes": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "element_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
})
```

Import `PptDiagnosticBuilder`, `PptReportStore`, and `ReportRefError`. Add helpers on the tool:

```python
def _report_store(self, project_dir: str) -> PptReportStore: ...
def _read_last_diagnostic(self, project_dir: str) -> dict[str, Any] | None: ...
def _diagnostic_result(self, state, operation: str, raw: dict[str, Any], summary: str) -> dict[str, Any]: ...
```

`_diagnostic_result` must:

1. Persist `raw` before compacting; persistence failure returns `REPORT_PERSIST_FAILED`.
2. Build diagnostic against `.editable-ppt/last_diagnostic.json`.
3. Save the current diagnostic to `last_diagnostic.json`.
4. Log `ppt_diagnostic_envelope_built` with operation, revision, raw character count, envelope character count, issue count, fingerprint, and status.
5. Return only project state, diagnostic, report ref, recommended action, suggested stage, and small operation-specific result facts.

Suggested stages are factual and nonbinding:

```python
if operation == "render" and diagnostic["issue_count"]:
    stage = "preview_fixing"
elif operation == "compile" and diagnostic["issue_count"]:
    stage = "compile_fixing"
elif operation == "compile" and raw.get("success"):
    stage = "validating"
elif operation == "validate" and raw.get("success"):
    stage = "ready_to_finalize"
else:
    stage = "source_draft"
```

- [ ] **Step 4: Integrate render, compile, validate, and read_report without breaking internal gates**

Change `render` to call `_diagnostic_result` instead of expanding `**result` into `_state_result`.

Change `compile` in this order:

1. Obtain raw compiler result.
2. On success, add `sourceRevision`, `sourceHashes`, and `pptxSha256` to the raw result.
3. Mark clean only on success.
4. Keep writing the complete raw result to `.editable-ppt/last_compile.json` because finalize reads it.
5. Return `_diagnostic_result(...)`, whose small facts include `pptx_path`, `slide_count`, `editable`, `forbidden_raster_fallbacks`, and measurement cache counts, but not screenshots, DOM trees, or full report.

Refactor validation into two methods:

```python
async def _run_validation_raw(self, project_dir: str, pptx_path: str | None) -> tuple[Any, str, dict[str, Any], bool]:
    """Return state, resolved path, complete validator result, and pass/fail."""

async def _validate(self, project_dir: str, pptx_path: str | None):
    state, path, raw, passed = await self._run_validation_raw(project_dir, pptx_path)
    self._record_json(project_dir, "last_validation.json", raw)
    return self._diagnostic_result(state, "validate", raw, raw.get("summary", "PPTX 验证完成"), success=passed)
```

Update `finalize` to call `_run_validation_raw` directly and pass the full raw validator payload to `build_editable_ppt_gate`; do not make finalize consume the compact Agent envelope.

Implement `read_report` through `PptReportStore.read`, accepting JSON-encoded arrays with the same validation convention as `render.pages`. Return the read payload under `data.report`. Catch `ReportRefError` and return `INVALID_REPORT_REF`.

- [ ] **Step 5: Run focused tool tests**

Run the command from Step 2.

Expected: all `test_tool.py` tests pass, including existing finalize and revision tests.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/tools/office/editable_ppt/tool.py backend/tests/tools/office/editable_ppt/test_tool.py
git commit -m "feat: return compact editable PPT diagnostics"
```

### Task 4: Make page-count requirements diagnosable before final delivery

**Files:**
- Modify: `backend/app/tools/office/editable_ppt/tool.py`
- Modify: `backend/tests/tools/office/editable_ppt/test_tool.py`

- [ ] **Step 1: Write failing requested-page-count tests**

Add optional `expected_slide_count` to the `render` and `compile` schema branches and these tests:

```python
@pytest.mark.asyncio
async def test_compile_returns_page_count_mismatch_as_actionable_deck_issue(tmp_path):
    tool = make_tool(tmp_path)
    created = await tool.execute(operation="create", title="十页汇报")

    result = await tool.execute(
        operation="compile",
        project_dir=created["data"]["project_dir"],
        expected_slide_count=10,
    )

    assert result["success"] is False
    issue = result["data"]["diagnostic"]["issues"][0]
    assert issue["code"] == "REQUESTED_PAGE_COUNT_MISMATCH"
    assert issue["source_path"] == "deck.json"
    assert issue["expected"] == 10
    assert issue["actual"] == 1
    assert result["data"]["recommended_action"]["source_paths"] == ["deck.json"]
```

Also assert a matching expected count leaves a successful compile successful.

- [ ] **Step 2: Run the two new tests and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/office/editable_ppt/test_tool.py -k page_count
```

Expected: schema/execution failures because `expected_slide_count` is not implemented.

- [ ] **Step 3: Inject a synthetic issue before diagnostic building**

Add schema property:

```python
"expected_slide_count": {"type": "integer", "minimum": 1}
```

Before passing render/compile raw results to `_diagnostic_result`, compare the expected count with `slideCount` from the compiler response or nested report. On mismatch, append this issue to a copied raw result and force public success to false:

```python
{
    "code": "REQUESTED_PAGE_COUNT_MISMATCH",
    "message": f"要求 {expected} 页，当前项目为 {actual} 页",
    "sourcePath": "deck.json",
    "expected": expected,
    "actual": actual,
    "severity": "error",
}
```

Do not mutate the compiler client's original dictionary in place. Do not mark a compile clean or write a deliverable compile record when the page-count contract fails; `.editable-ppt/last_compile.json` must record the failed augmented raw result so finalize rejects it.

- [ ] **Step 4: Run full tool tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/office/editable_ppt/test_tool.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/app/tools/office/editable_ppt/tool.py backend/tests/tools/office/editable_ppt/test_tool.py
git commit -m "feat: diagnose editable PPT page-count mismatches"
```

### Task 5: Upgrade the PPT Agent workflow contract

**Files:**
- Modify: `backend/app/tools/office/editable_ppt/references/workflow.md`
- Modify: `backend/app/agent/prompts/ppt_prompt.py`
- Modify: `backend/app/agent/prompts/ppt_mode_spec.py`

- [ ] **Step 1: Add failing prompt contract assertions**

Extend `test_ppt_mode_prompt_uses_editable_incremental_workflow_by_default` with:

```python
assert "诊断是定位索引，不是源码" in prompt
assert "修改前必须读取" in prompt
assert "diagnostic.status=unchanged" in prompt
assert "不得立即重复同一种修改" in prompt
assert "一次读取全部受影响源码" in prompt
assert "expected_slide_count" in prompt
```

Add a test that reads `workflow.md` and asserts the seven approved headings and the ordering of the critical loop:

```python
def test_ppt_workflow_defines_diagnostic_driven_stage_protocol():
    workflow = Path("app/tools/office/editable_ppt/references/workflow.md").read_text(encoding="utf-8")
    headings = ["材料理解", "大纲规划", "初稿生成", "低成本预览", "批量修复", "严格编译", "验证与交付"]
    assert all(f"## {index}. {heading}" in workflow for index, heading in enumerate(headings, 1))
    assert workflow.index("读取全部受影响源码") < workflow.index("edit_sources")
    assert "read_report" in workflow
    assert "原始报告只有在结构化诊断不足时" in workflow
```

- [ ] **Step 2: Run prompt tests and verify failure**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/prompts/ppt_mode_spec.py
```

Expected: new assertions fail against the current advisory prompt/workflow.

- [ ] **Step 3: Rewrite workflow.md as the approved stage protocol**

Retain the current source-project model, native object contract, edit/revision rules, strict CSS restrictions, and performance baseline. Replace `推荐步骤` with these numbered sections and explicit exit conditions:

1. 材料理解：read once, produce structured brief, only targeted rereads.
2. 大纲规划：exact page plan; every page has purpose, conclusion, source, layout; page count must match.
3. 初稿生成：batch theme/deck/all sources; inspect files, references, revision, page count.
4. 低成本预览：consume diagnostic envelope; read all affected sources; use `read_report` only if evidence is insufficient.
5. 批量修复：group by root cause; one `edit_sources` where practical; record revision and fingerprint.
6. 严格编译：pass `expected_slide_count`; handle `resolved`, `changed`, and `unchanged` exactly as approved.
7. 验证与交付：strict compile → validate → finalize → present.

Add the approved behavior constraints verbatim enough for prompt tests to lock them: diagnosis is an index rather than source, read before edit, process all pages, do not regenerate the deck for a local issue, and explain why the next compile should change the named diagnosis.

- [ ] **Step 4: Update the focused PPT system prompt**

In `ppt_prompt.py`, keep the prompt concise and route detail to `workflow.md`. Add a `诊断驱动修复` subsection containing:

```text
- render/compile/validate 默认返回结构化诊断和 report_ref。诊断是定位索引，不是源码；修改前必须读取 diagnostic.issues 对应的 source_path。
- 一次诊断涉及多个页面时，一次读取全部受影响源码，按共同根因分析，并优先用单次 edit_sources 批量修复。
- 只有结构化诊断证据不足时才用 read_report 按页面、错误码或元素读取原始报告；不要无条件读取完整报告。
- diagnostic.status=unchanged 表示上轮修改没有改变问题；必须重新读取源码和证据、重新判断根因，不得立即重复同一种修改。
- 用户指定页数时，render/compile 传 expected_slide_count；页数不符不得进入交付。
```

- [ ] **Step 5: Run prompt tests**

Run the command from Step 2.

Expected: all prompt contract tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add backend/app/tools/office/editable_ppt/references/workflow.md backend/app/agent/prompts/ppt_prompt.py backend/app/agent/prompts/ppt_mode_spec.py
git commit -m "docs: guide PPT agent with structured diagnostics"
```

### Task 6: Real compiler regression and end-to-end quality verification

**Files:**
- Modify: `backend/tests/tools/office/editable_ppt/test_e2e.py`
- Modify if defects are exposed: `backend/app/tools/office/editable_ppt/diagnostics.py`
- Modify if defects are exposed: `backend/app/tools/office/editable_ppt/tool.py`

- [ ] **Step 1: Update the real ten-slide regression for compact responses**

The current E2E test reads the entire compile report from the tool response. Change it to assert the public compact facts and then read the raw report through `read_report`:

```python
first = await tool.execute(
    operation="compile",
    project_dir=str(project_dir),
    expected_slide_count=10,
)
assert first["success"] is True
assert first["data"]["slide_count"] == 10
assert first["data"]["diagnostic"]["issue_count"] == 0
assert len(json.dumps(first, ensure_ascii=False)) < 10_000

first_raw = await tool.execute(
    operation="read_report",
    project_dir=str(project_dir),
    report_ref=first["data"]["report_ref"],
)
assert first_raw["data"]["report"]["report"]["slideCount"] == 10
assert first_raw["data"]["report"]["report"]["measurement"]["cache"] == {
    "enabled": True, "hits": 0, "misses": 10
}
```

After editing slide 3, assert the second compact response is successful and its raw report has nine cache hits and one miss. Import `json` at the top of the test.

- [ ] **Step 2: Run the focused non-browser suite first**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/tests/tools/office/editable_ppt/test_report_store.py \
  backend/tests/tools/office/editable_ppt/test_diagnostics.py \
  backend/tests/tools/office/editable_ppt/test_tool.py \
  backend/app/agent/prompts/ppt_mode_spec.py
```

Expected: all tests pass.

- [ ] **Step 3: Run the real browser/compiler E2E**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/tools/office/editable_ppt/test_e2e.py \
  -m "integration and browser" -v
```

Expected: the ten-slide compile passes twice; the second compile remeasures only one dirty slide; compact responses remain below 10 KB; the complete reports are readable by reference.

- [ ] **Step 4: Run the complete editable-PPT regression suite**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/tools/office/editable_ppt app/agent/prompts/ppt_mode_spec.py
```

Expected: all tests pass, with only deliberately deselected performance tests if their environment flag is absent.

- [ ] **Step 5: Inspect diagnostic size evidence**

Run a single synthetic failing compile test with logs enabled:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q -s \
  tests/tools/office/editable_ppt/test_tool.py \
  -k "compact_complete_diagnostic or unchanged"
```

Expected: `ppt_diagnostic_envelope_built` includes `raw_chars > envelope_chars`, the full issue count, and correct `new`/`unchanged` status. No full DOM tree appears in the returned tool result.

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/tests/tools/office/editable_ppt/test_e2e.py backend/app/tools/office/editable_ppt/diagnostics.py backend/app/tools/office/editable_ppt/tool.py
git commit -m "test: verify compact PPT diagnostic workflow"
```

### Task 7: Final verification against the approved specification

**Files:**
- Verify only; modify only files already listed if a check exposes a defect.

- [ ] **Step 1: Run formatting and whitespace checks**

```bash
git diff --check c79ff23..HEAD
```

Expected: no whitespace errors.

- [ ] **Step 2: Run all focused Python tests once more from the documented environment**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/tools/office/editable_ppt app/agent/prompts/ppt_mode_spec.py
```

Expected: all tests pass.

- [ ] **Step 3: Verify no generic Agent context files changed**

```bash
git diff --name-only c79ff23..HEAD | rg '^backend/app/agent/(context|runtime)/'
```

Expected: no output. This confirms the first release remains PPT-tool-specific.

- [ ] **Step 4: Verify the public tool response is complete but compact**

Run:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/tools/office/editable_ppt/test_tool.py \
  -k "compact_complete_diagnostic or read_report or page_count or unchanged" -v
```

Expected: all selected tests pass, proving complete issue enumeration, safe report recovery, exact page-count feedback, and stable unchanged detection.

- [ ] **Step 5: Review working tree scope**

```bash
git status --short
git log --oneline --max-count=8
```

Expected: only pre-existing unrelated files, if any, remain untracked or modified; PPT diagnostic implementation commits are present.

## Completion criteria

The implementation is complete only when:

- Every raw render/compile/validate report is preserved and addressable by safe `report_ref`.
- Every actionable issue is present in the diagnostic envelope; unknown shapes are not silently dropped.
- Agent-facing results omit large measurement trees and repeated report payloads.
- Diagnostics provide stable page/slide/element/source references and `new`/`changed`/`unchanged`/`resolved` status.
- `read_report` returns exact filtered raw evidence without escaping the PPT project.
- The PPT workflow requires read-source-before-edit and multi-page batch repair.
- User-specified page counts are explicitly checked.
- Existing strict compile, validation, finalize, incremental cache, and delivery guards still pass.
