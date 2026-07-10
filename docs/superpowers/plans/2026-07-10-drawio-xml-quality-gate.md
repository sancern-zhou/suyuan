# Draw.io XML Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject structurally unreliable draw.io XML, report non-blocking readability warnings, and make the chart-mode guidance drive an inspect-and-revise workflow.

**Architecture:** Keep parsing and mutation in `xml_utils.py`, add a small `quality_gate.py` module that owns structured diagnostics, and expose its report through `CreateDrawioBoardTool`. Update the existing draw.io guide router and XML contract instead of creating a separate skill runtime.

**Tech Stack:** Python 3.11, `xml.etree.ElementTree`, pytest, Markdown Agent guides

---

### Task 1: Strengthen deterministic XML validation

**Files:**
- Modify: `backend/app/tools/visualization/create_drawio_board/xml_utils.py`
- Test: `backend/app/tools/visualization/create_drawio_board/xml_utils_test.py`

- [ ] **Step 1: Write failing tests for invalid structure**

Add focused tests asserting that `normalize_drawio_xml` raises `DrawioXmlError` for a dangling parent, missing vertex geometry, non-positive vertex dimensions, non-finite coordinates, an edge without relative geometry, and raw or escaped HTML tags in `value`. Add a positive test showing `&#xa;` newline content remains valid.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/app/tools/visualization/create_drawio_board/xml_utils_test.py -q
```

Expected: the new cases fail because current validation checks only IDs and edge endpoints.

- [ ] **Step 3: Implement minimal structural checks**

Extend `_validate_cells` with small helpers that:

```python
def _validate_references(cell: ET.Element, known_ids: set[str]) -> None: ...
def _validate_vertex_geometry(cell: ET.Element) -> None: ...
def _validate_edge_geometry(cell: ET.Element) -> None: ...
def _validate_plain_text_value(cell: ET.Element) -> None: ...
```

Use `math.isfinite(float(value))` for geometry values. Require `x`, `y`, `width`, and `height` for vertices, positive dimensions, and `relative="1"` for edges. Detect tag-shaped raw or once-unescaped text with a bounded regular expression rather than rejecting ordinary `<` comparisons.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command and expect all tests to pass.

### Task 2: Add advisory quality diagnostics

**Files:**
- Create: `backend/app/tools/visualization/create_drawio_board/quality_gate.py`
- Create: `backend/app/tools/visualization/create_drawio_board/quality_gate_test.py`

- [ ] **Step 1: Write failing diagnostics tests**

Define the desired API in tests:

```python
report = inspect_drawio_quality(normalized_xml)
assert report["status"] == "warning"
assert {issue["code"] for issue in report["warnings"]} >= {"overlapping_vertices"}
```

Cover overlap, long vertex labels, long edge labels, missing `whiteSpace=wrap`, `html=1`, metrics, and exclusion of text/title cells, containers, nested children, and boundary-touching rectangles.

- [ ] **Step 2: Run diagnostics tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/app/tools/visualization/create_drawio_board/quality_gate_test.py -q
```

Expected: collection fails because `quality_gate.py` does not exist.

- [ ] **Step 3: Implement the quality inspector**

Create:

```python
def inspect_drawio_quality(xml: str) -> dict[str, Any]: ...
```

Parse normalized XML, collect cells, count vertices and edges, and emit stable issue dictionaries with `code`, `cell_id`, and `message`. Use explicit conservative constants for label lengths and a positive-area rectangle intersection test. Treat swimlanes/containers, `text` styles, and non-top-level cells as overlap exclusions.

- [ ] **Step 4: Run diagnostics tests and verify GREEN**

Run the Task 2 command and expect all tests to pass.

### Task 3: Return quality reports from the board tool

**Files:**
- Modify: `backend/app/tools/visualization/create_drawio_board/tool.py`
- Modify: `backend/app/tools/visualization/create_drawio_board/tool_test.py`

- [ ] **Step 1: Write failing tool contract tests**

Add tests asserting:

```python
assert result["data"]["quality_report"]["status"] == "pass"
```

and that a board with advisory issues succeeds, returns `status="warning"`, and mentions the warning count in `summary`. Confirm invalid XML still returns `success=False` and is not stored.

- [ ] **Step 2: Run tool tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/app/tools/visualization/create_drawio_board/tool_test.py -q
```

Expected: new assertions fail because the tool does not return `quality_report`.

- [ ] **Step 3: Integrate the inspector**

After normalization/editing and before storage:

```python
quality_report = inspect_drawio_quality(normalized_xml)
```

Attach it to `data`; update `_build_summary` to append a concise warning count while preserving existing create/edit wording. Do not change frontend contracts or artifact storage fields.

- [ ] **Step 4: Run tool tests and verify GREEN**

Run the Task 3 command and expect all tests to pass.

### Task 4: Tighten progressive draw.io guidance

**Files:**
- Modify: `backend/app/agent/guides/drawio_board_workflow.md`
- Modify: `backend/app/agent/guides/drawio_xml_rules.md`
- Create: `backend/app/agent/guides/drawio_quality_checklist.md`
- Modify: `backend/app/tools/visualization/create_drawio_board/tool.py`
- Test: `backend/app/agent/prompts/task_tool_registry_test.py`

- [ ] **Step 1: Write failing guidance contract assertions**

Update the prompt/tool registry test to require the tool description or assembled chart prompt to reference `drawio_quality_checklist.md`, `quality_report`, and the inspect-and-revise step.

- [ ] **Step 2: Run the prompt test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/app/agent/prompts/task_tool_registry_test.py -q
```

Expected: new string assertions fail.

- [ ] **Step 3: Update the guides**

Align XML rules to plain-text `value` and `html=0`; document hard errors separately from warnings. Add a compact quality checklist covering type/direction, semantic IDs, geometry, label length, connectors, color semantics, and `quality_report` repair. Update the workflow and tool description so the checklist is loaded before first create and warnings are repaired when they affect readability.

- [ ] **Step 4: Run prompt and draw.io tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/app/agent/prompts/task_tool_registry_test.py \
  backend/app/tools/visualization/create_drawio_board/xml_utils_test.py \
  backend/app/tools/visualization/create_drawio_board/quality_gate_test.py \
  backend/app/tools/visualization/create_drawio_board/tool_test.py -q
```

Expected: all tests pass.

### Task 5: Final regression verification

**Files:**
- Verify only

- [ ] **Step 1: Run related chart-mode tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/app/agent/prompts/task_tool_registry_test.py \
  backend/app/agent/runtime/drawio_board_context_injection_test.py \
  backend/app/agent/memory/session_memory_drawio_test.py \
  backend/app/routers/agent_drawio_board_persistence_test.py \
  backend/app/tools/visualization/create_drawio_board -q
```

Expected: all tests pass without warnings or collection errors.

- [ ] **Step 2: Inspect the final diff**

Run `git diff --check` and confirm only the intended draw.io files plus this plan/spec are part of the work. Do not stage or modify unrelated existing worktree changes.
