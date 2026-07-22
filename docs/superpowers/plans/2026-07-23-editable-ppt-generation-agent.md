# Editable PPT Generation Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-first PPT generation Agent that renders editable HTML/Tailwind slide projects into native PPTX objects, supports repeated direct document edits without regenerating unchanged content, and reuses Suyuan's validation and artifact delivery pipeline.

**Architecture:** A sandboxed Node runtime loads versioned `deck.json`, `theme.json`, and `slide-N.js` source documents, renders them in a fixed browser canvas, measures DOM geometry, and compiles native PPTX objects with PptxGenJS through isolated adapters. Python owns project revisions, dirty dependency tracking, safe source edits, Node subprocess execution, LLM tool schemas, validation, and artifact attachment. The existing PPT Master tool remains available and unchanged.

**Tech Stack:** Python 3.11, pytest, Node.js 20+, Node test runner, Vite 5, Tailwind CSS, Puppeteer, dom-to-pptx 2.1.1 behind an adapter, PptxGenJS 4.0.1, JSZip, LibreOffice QA

---

## Scope decomposition

The approved specification covers four subsystems, but they are implemented here as one ordered vertical plan so every checkpoint leaves testable software:

1. Node source/preview/compiler technical foundation.
2. Python project lifecycle and incremental editing.
3. Agent tool exposure and workflow guidance.
4. QA, representative themes/layouts, and long-deck acceptance.

Existing-upload PPTX editing remains outside this plan.

## File map

### Node runtime

- `backend/app/tools/office/editable_ppt_runtime/package.json`: pinned isolated dependencies and test scripts.
- `backend/app/tools/office/editable_ppt_runtime/package-lock.json`: reproducible dependency graph.
- `backend/app/tools/office/editable_ppt_runtime/src/contracts.mjs`: schema constants and validation.
- `backend/app/tools/office/editable_ppt_runtime/src/source_loader.mjs`: sandboxed project and slide loading.
- `backend/app/tools/office/editable_ppt_runtime/src/preview_project.mjs`: generated immutable preview shell.
- `backend/app/tools/office/editable_ppt_runtime/src/measure.mjs`: Puppeteer lifecycle, readiness, screenshots, and DOM measurements.
- `backend/app/tools/office/editable_ppt_runtime/src/pptx/basic_adapter.mjs`: native text/shape/image conversion and dom-to-pptx boundary.
- `backend/app/tools/office/editable_ppt_runtime/src/pptx/semantic_adapter.mjs`: native chart/table/diagram conversion.
- `backend/app/tools/office/editable_ppt_runtime/src/pptx/strict_policy.mjs`: editable policy and fallback auditing.
- `backend/app/tools/office/editable_ppt_runtime/src/compile.mjs`: deterministic deck compiler and report writer.
- `backend/app/tools/office/editable_ppt_runtime/src/cli.mjs`: JSON-line CLI contract.
- `backend/app/tools/office/editable_ppt_runtime/runtime/*`: immutable Vite/Tailwind preview client.
- `backend/app/tools/office/editable_ppt_runtime/test/*`: Node unit, contract, and integration tests.

### Python service and Agent integration

- `backend/app/tools/office/editable_ppt/__init__.py`: public exports.
- `backend/app/tools/office/editable_ppt/contracts.py`: typed project/report contracts.
- `backend/app/tools/office/editable_ppt/project_service.py`: creation, safe reads/edits, revisions, snapshots, dependency hashes.
- `backend/app/tools/office/editable_ppt/compiler_client.py`: timeout-safe Node CLI client.
- `backend/app/tools/office/editable_ppt/tool.py`: `manage_editable_ppt` LLM tool and complete schema.
- `backend/app/tools/office/editable_ppt/references/index.md`: progressive workflow entry.
- `backend/app/tools/office/editable_ppt/references/workflow.md`: source-first Agent instructions.
- `backend/app/tools/__init__.py`: global tool registration.
- `backend/app/agent/prompts/tool_registry.py`: assistant-mode exposure.
- `backend/app/agent/skill_metadata.py`: selectable scenario metadata.
- `backend/app/tools/office/office_skills_guide.md`: routing between PPT Master and editable PPT Agent.
- `backend/tests/tools/office/editable_ppt/*`: Python unit and integration tests.
- `backend/tests/test_assistant_ppt_tool_exposure.py`: registry compatibility.

### QA and acceptance fixtures

- `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/*`: ten-slide acceptance source project.
- `backend/app/tools/office/editable_ppt_runtime/fixtures/themes/*`: government, business, and data-analysis themes.
- `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/*`: first reusable layouts.
- `backend/app/tools/office/editable_ppt/quality.py`: compile/validation gate merger.
- `backend/tests/tools/office/editable_ppt/test_quality.py`: strict editability and delivery gate tests.

---

### Task 1: Isolated Node runtime and contract validator

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/package.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/package-lock.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/src/contracts.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/contracts.test.mjs`

- [ ] **Step 1: Write the failing contract tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { validateDeck, validateSlide } from "../src/contracts.mjs";

test("deck requires schema version, stable id, theme, and ordered slides", () => {
  assert.deepEqual(validateDeck({}), {
    ok: false,
    errors: ["schemaVersion is required", "id is required", "theme is required", "slides must be a non-empty array"],
  });
});

test("slide accepts HTML plus native chart data with stable ids", () => {
  const result = validateSlide({
    schemaVersion: "1.0",
    id: "growth",
    type: "data-analysis",
    intent: "show growth",
    layoutMode: "freeform",
    html: '<section><div data-pptx-ref="chart-1"></div></section>',
    nativeElements: [{
      id: "chart-1",
      kind: "chart",
      chartType: "column",
      data: { categories: ["2025"], series: [{ name: "收入", values: [10] }] },
    }],
    speakerNotes: [],
  });
  assert.equal(result.ok, true);
});
```

- [ ] **Step 2: Run the Node tests and verify RED**

Run:

```bash
cd backend/app/tools/office/editable_ppt_runtime
npm test -- --test-name-pattern=deck
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/contracts.mjs`.

- [ ] **Step 3: Add the pinned package and minimal validator**

Create `package.json` with `type: module`, test script `node --test`, and exact dependencies `dom-to-pptx: 2.1.1`, `pptxgenjs: 4.0.1`, `puppeteer: 25.1.0`, `vite: 5.4.10`, `tailwindcss: 4.1.0`, `@tailwindcss/vite: 4.1.0`, and `jszip: 3.10.1`. Implement `validateDeck` and `validateSlide` as pure functions returning `{ok, errors}`; validate stable IDs, supported layout modes, native element kinds, unique element IDs, chart series lengths, and `data-pptx-ref` references.

```javascript
export const SCHEMA_VERSION = "1.0";
export const LAYOUT_MODES = new Set(["template", "freeform", "hybrid"]);
export const NATIVE_KINDS = new Set(["chart", "table", "diagram"]);

export function validateDeck(deck) {
  const errors = [];
  if (!deck?.schemaVersion) errors.push("schemaVersion is required");
  if (!deck?.id) errors.push("id is required");
  if (!deck?.theme) errors.push("theme is required");
  if (!Array.isArray(deck?.slides) || deck.slides.length === 0) errors.push("slides must be a non-empty array");
  return { ok: errors.length === 0, errors };
}
```

- [ ] **Step 4: Install dependencies and run GREEN**

Run:

```bash
cd backend/app/tools/office/editable_ppt_runtime
npm install
npm test
```

Expected: package lock is created and all contract tests pass.

- [ ] **Step 5: Commit the contract foundation**

```bash
git add backend/app/tools/office/editable_ppt_runtime
git commit -m "feat: add editable ppt runtime contracts"
```

### Task 2: Sandboxed source project loader

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/src/source_loader.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/source_loader.test.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/fixtures/project/deck.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/fixtures/project/theme.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/fixtures/project/slides/slide-001.js`

- [ ] **Step 1: Write tests for direct documents and sandbox denial**

```javascript
test("loads slideDataMap registrations in numeric order", async () => {
  const project = await loadProject(fixture("project"));
  assert.equal(project.slides[0].id, "cover");
  assert.equal(project.slides[0].html.includes("年度报告"), true);
});

test("slide source cannot access process or require", async () => {
  await assert.rejects(
    () => loadSlideSource('process.exit(1); window.slideDataMap.set(1, {});', "malicious.js"),
    /process is not defined/,
  );
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run `npm test -- --test-name-pattern=sandbox`. Expected: module import failure.

- [ ] **Step 3: Implement the VM loader**

Use `node:vm` with a context containing only a frozen `window.slideDataMap`, no `process`, `require`, `fetch`, timers, or dynamic imports. Set a 200 ms script timeout, require exactly one registration per file, reject duplicate page numbers, resolve only descendants of the project root, and call the Task 1 validators after loading.

```javascript
export function loadSlideSource(source, filename) {
  const slideDataMap = new Map();
  const context = vm.createContext({ window: Object.freeze({ slideDataMap }) });
  new vm.Script(source, { filename }).runInContext(context, { timeout: 200 });
  if (slideDataMap.size !== 1) throw new Error(`${filename} must register exactly one slide`);
  return [...slideDataMap.entries()][0];
}
```

- [ ] **Step 4: Verify path traversal, duplicate IDs, and normal loading**

Run `npm test`. Expected: all loader and contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime/src/source_loader.mjs backend/app/tools/office/editable_ppt_runtime/test
git commit -m "feat: load editable ppt source projects safely"
```

### Task 3: Immutable Vite/Tailwind preview runtime

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/runtime/index.html`
- Create: `backend/app/tools/office/editable_ppt_runtime/runtime/main.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/runtime/controller.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/runtime/input.css`
- Create: `backend/app/tools/office/editable_ppt_runtime/src/preview_project.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/preview_project.test.mjs`

- [ ] **Step 1: Write the failing preview generation test**

```javascript
test("materializes immutable runtime with project data and Tailwind source", async () => {
  const out = await materializePreview(projectDir, buildDir);
  assert.equal(await exists(path.join(out, "index.html")), true);
  assert.match(await read("input.css"), /@source .*slides/);
  const payload = JSON.parse(await read("deck-runtime.json"));
  assert.equal(payload.slides.length, 1);
});
```

- [ ] **Step 2: Run and verify RED**

Run `npm test -- --test-name-pattern=materializes`. Expected: missing module.

- [ ] **Step 3: Implement preview materialization**

Copy runtime-owned files into `.editable-ppt-runtime/`, serialize validated slide data into `deck-runtime.json`, and generate an `input.css` containing Tailwind import plus an absolute `@source` for project slide files. `main.mjs` renders the requested `?page=N`, maps theme tokens to CSS variables, renders chart/table/diagram Web previews from native data, and sets `window.__PPT_READY__ = true` only after `document.fonts.ready` and all images settle.

- [ ] **Step 4: Test routing and framework immutability**

Add assertions that page 1 is the default, invalid page numbers return a visible error, keyboard handlers call the controller, and no runtime-owned file lives under editable `slides/` or `templates/`. Run `npm test`; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime/runtime backend/app/tools/office/editable_ppt_runtime/src/preview_project.mjs backend/app/tools/office/editable_ppt_runtime/test/preview_project.test.mjs
git commit -m "feat: add editable ppt preview runtime"
```

### Task 4: Browser measurement, screenshots, and runtime diagnostics

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/src/measure.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/measure.test.mjs`

- [ ] **Step 1: Write browser tests for readiness and overflow**

```javascript
test("measures a 1440x810 slide and reports overflowing nodes", async () => {
  const result = await measureDeck(fixtureProject, outputDir, { pages: [1] });
  assert.deepEqual(result.viewport, { width: 1440, height: 810 });
  assert.equal(result.pages[0].elements.some((item) => item.id === "title"), true);
  assert.equal(result.pages[0].issues[0].code, "ELEMENT_OUT_OF_BOUNDS");
  assert.equal(await exists(result.pages[0].screenshotPath), true);
});
```

- [ ] **Step 2: Run with browser marker and verify RED**

Run `npm test -- --test-name-pattern=measures`. Expected: missing `measure.mjs`.

- [ ] **Step 3: Implement one-browser/many-pages measurement**

Launch one Puppeteer browser per command, start Vite on an ephemeral loopback port, visit each requested page, wait at most 30 seconds for `__PPT_READY__`, and evaluate every element carrying `data-pptx-id` or `data-pptx-ref`. Return bounding boxes, computed text styles, fills, borders, opacity, z-index, overflow, duplicate references, missing assets, and screenshots. Always close page, browser, and Vite server in `finally`.

- [ ] **Step 4: Run Node tests**

Run `npm test`. Expected: all tests pass; browser tests skip with a clear message only when Chromium is unavailable.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime/src/measure.mjs backend/app/tools/office/editable_ppt_runtime/test/measure.test.mjs
git commit -m "feat: measure editable ppt slides in chromium"
```

### Task 5: Strict policy and native PPTX adapters

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/src/pptx/strict_policy.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/src/pptx/basic_adapter.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/src/pptx/semantic_adapter.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/pptx_adapters.test.mjs`

- [ ] **Step 1: Write failing adapter tests**

```javascript
test("strict mode rejects text rasterization", () => {
  assert.throws(() => assertEditable({ kind: "text", fallback: "png" }, "strict"), /RASTER_FALLBACK_FORBIDDEN/);
});

test("semantic adapters emit native chart, table, and diagram calls", () => {
  const slide = fakeSlideRecorder();
  addNativeElement(slide, chartFixture, chartBox, theme);
  addNativeElement(slide, tableFixture, tableBox, theme);
  addNativeElement(slide, diagramFixture, diagramBox, theme);
  assert.deepEqual(slide.calls.map((call) => call.method), ["addChart", "addTable", "addShape", "addText", "addShape"]);
});
```

- [ ] **Step 2: Run and verify RED**

Run `npm test -- --test-name-pattern="strict|semantic"`. Expected: missing adapter modules.

- [ ] **Step 3: Implement adapters**

`basic_adapter.mjs` maps measured text, rectangles, lines, images, fills, borders, and supported shadows to PptxGenJS calls. Keep `dom-to-pptx` behind `convertCommonDom()` so it can be disabled by configuration; unsupported or raster-producing results become structured issues instead of images in strict mode. `semantic_adapter.mjs` maps chart data to `addChart`, table matrices to `addTable`, and diagram nodes/edges to grouped native shapes and connectors using the measured placeholder box.

- [ ] **Step 4: Add unit conversion and editability count assertions**

Test `1440px -> 13.333in`, `810px -> 7.5in`, no `#` prefixes in PptxGenJS colors, chart category/series length mismatch errors, editable table cells, and diagram node/edge IDs. Run `npm test`; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime/src/pptx backend/app/tools/office/editable_ppt_runtime/test/pptx_adapters.test.mjs
git commit -m "feat: compile native editable ppt objects"
```

### Task 6: Deterministic compiler, OOXML audit, and CLI

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/src/compile.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/src/cli.mjs`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/compile.test.mjs`
- Modify: `backend/app/tools/office/editable_ppt_runtime/package.json`

- [ ] **Step 1: Write an end-to-end compiler test**

```javascript
test("compile writes pptx and strict compile report", async () => {
  const result = await compileDeck(fixtureProject, outputDir, { editable: "strict" });
  assert.equal(result.success, true);
  assert.equal(await exists(result.pptxPath), true);
  assert.equal(result.report.forbiddenRasterFallbacks, 0);
  assert.equal(result.report.native.chart, 1);
  assert.equal(result.report.native.table, 1);
});
```

- [ ] **Step 2: Run and verify RED**

Run `npm test -- --test-name-pattern="compile writes"`. Expected: missing compiler.

- [ ] **Step 3: Implement compile orchestration and JSON-line CLI**

Support commands `inspect`, `preview`, `compile`, and `health`. Every command reads one JSON object from stdin and writes one JSON object to stdout; logs go to stderr. Compile validated slides in deck order, add stable object names, write `presentation.pptx` and `compile-report.json`, inspect the ZIP with JSZip for required slide/chart/embedding relationships, and return structured issues.

```javascript
const handlers = { inspect: inspectProject, preview: renderPreview, compile: compileDeck, health: healthCheck };
const request = JSON.parse(await readStdin());
const handler = handlers[request.command];
if (!handler) throw new Error(`unsupported command: ${request.command}`);
process.stdout.write(`${JSON.stringify(await handler(request))}\n`);
```

- [ ] **Step 4: Verify CLI success and malformed request errors**

Run:

```bash
printf '%s\n' '{"command":"health"}' | node src/cli.mjs
npm test
```

Expected: health returns `{success:true}` and tests cover malformed JSON, timeout, strict failure, native object counts, and ZIP relationships.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime
git commit -m "feat: add editable ppt compiler cli"
```

### Task 7: Python project contracts and source-first revision service

**Files:**
- Create: `backend/app/tools/office/editable_ppt/__init__.py`
- Create: `backend/app/tools/office/editable_ppt/contracts.py`
- Create: `backend/app/tools/office/editable_ppt/project_service.py`
- Create: `backend/tests/tools/office/editable_ppt/test_project_service.py`

- [ ] **Step 1: Write failing Python tests**

```python
def test_edit_source_changes_only_dependent_slide(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告", theme="government")
    before = service.inspect(project.project_dir)
    result = service.edit_source(
        project.project_dir,
        relative_path="slides/slide-001.js",
        content=SLIDE_1_REVISED,
        base_revision=before.revision,
    )
    assert result.revision == before.revision + 1
    assert result.dirty_slides == ["cover"]

def test_edit_rejects_path_escape_and_stale_revision(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告", theme="government")
    with pytest.raises(ValueError, match="outside project root"):
        service.edit_source(
            project.project_dir,
            relative_path="../outside.js",
            content="bad",
            base_revision=project.revision,
        )

def test_inspect_reconciles_a_direct_file_edit(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告", theme="government")
    slide_path = Path(project.project_dir) / "slides" / "slide-001.js"
    slide_path.write_text(SLIDE_1_REVISED, encoding="utf-8")
    reconciled = service.inspect(project.project_dir)
    assert reconciled.revision == project.revision + 1
    assert reconciled.dirty_slides == ["cover"]
    assert reconciled.changes[-1].source == "direct_document_edit"
    service.edit_source(
        project.project_dir,
        relative_path="slides/slide-001.js",
        content=SLIDE_1_REVISED,
        base_revision=project.revision,
    )
    with pytest.raises(RevisionConflictError):
        service.edit_source(
            project.project_dir,
            relative_path="slides/slide-001.js",
            content=SLIDE_1_REVISED_AGAIN,
            base_revision=project.revision,
        )
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt/test_project_service.py
```

Expected: import failure for `app.tools.office.editable_ppt`.

- [ ] **Step 3: Implement project creation, edits, revisions, and snapshots**

Use dataclasses for `ProjectState`, `EditResult`, and `DirtyState`. Create projects only below `get_data_registry()/editable_ppt_projects`, slug and randomize directory names, write starter `deck.json`, `theme.json`, and `slides/slide-001.js`, and atomically update `.editable-ppt/state.json`. Before every managed edit, validate the resolved path is a descendant, compare `base_revision`, snapshot changed files, compute SHA-256 hashes, and derive dirty slides from deck/theme/asset/slide references. Before inspect, render, or compile, call `reconcile_external_edits()`: compare current hashes with the last checkpoint, classify changes made through the ordinary `edit_file` tool as `direct_document_edit`, increment the revision once for the detected batch, and propagate dirty dependencies without rewriting the edited source.

- [ ] **Step 4: Test restore and dependency propagation**

Add tests proving managed and direct slide edits dirty one page, image edits dirty only consumers, theme font changes dirty all slides, stale revisions fail without writes, and `restore_revision()` restores source plus dirty state. Run the focused pytest command; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt backend/tests/tools/office/editable_ppt/test_project_service.py
git commit -m "feat: manage editable ppt source revisions"
```

### Task 8: Timeout-safe Python compiler client and cache protocol

**Files:**
- Create: `backend/app/tools/office/editable_ppt/compiler_client.py`
- Create: `backend/tests/tools/office/editable_ppt/test_compiler_client.py`

- [ ] **Step 1: Write failing async client tests**

```python
@pytest.mark.asyncio
async def test_compile_sends_one_json_request_and_parses_response(tmp_path, monkeypatch):
    process = FakeProcess(stdout=b'{"success":true,"dirtySlides":["cover"]}\n')
    monkeypatch.setattr(asyncio, "create_subprocess_exec", process.factory)
    result = await EditablePptCompilerClient().compile(tmp_path, dirty_slides=["cover"])
    assert result["success"] is True
    assert json.loads(process.stdin_payload)["dirtySlides"] == ["cover"]
```

- [ ] **Step 2: Run and verify RED**

Run the focused test. Expected: missing compiler client.

- [ ] **Step 3: Implement the client**

Resolve Node and `src/cli.mjs` explicitly, call `asyncio.create_subprocess_exec`, send JSON via stdin, collect stdout/stderr with a configurable timeout, terminate on timeout, reject multiple stdout objects, and surface `NODE_RUNTIME_MISSING`, `COMPILER_TIMEOUT`, `COMPILER_PROTOCOL_ERROR`, and compiler-reported issue codes. Pass dirty slide IDs and cache directory to preview/compile commands.

- [ ] **Step 4: Run timeout and protocol tests**

Cover nonzero exit, stderr diagnostics, invalid JSON, timeout termination, missing Node, and successful response. Run focused pytest; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt/compiler_client.py backend/tests/tools/office/editable_ppt/test_compiler_client.py
git commit -m "feat: invoke editable ppt compiler safely"
```

### Task 9: Complete Agent tool schema and operations

**Files:**
- Create: `backend/app/tools/office/editable_ppt/tool.py`
- Create: `backend/tests/tools/office/editable_ppt/test_tool.py`

- [ ] **Step 1: Write schema and operation tests**

Require `manage_editable_ppt` to use operation-specific `oneOf` branches for `create`, `inspect`, `read_source`, `edit_source`, `render`, `compile`, `validate`, `restore`, and `finalize`. Verify `edit_source` requires `project_dir`, `relative_path`, `content`, and `base_revision`; compile defaults to strict editability.

```python
def test_schema_exposes_direct_document_edit_contract():
    schema = ManageEditablePptTool().get_function_schema()
    branches = schema["parameters"]["oneOf"]
    edit = next(branch for branch in branches if branch["properties"]["operation"]["const"] == "edit_source")
    assert set(edit["required"]) == {"operation", "project_dir", "relative_path", "content", "base_revision"}
```

- [ ] **Step 2: Run and verify RED**

Run `pytest -q tests/tools/office/editable_ppt/test_tool.py`. Expected: missing tool.

- [ ] **Step 3: Implement operations and stable result contract**

Delegate source operations to `EditablePptProjectService`, preview/compile to `EditablePptCompilerClient`, validation to `ValidatePptxTool`, and artifact attachment to existing helpers. Every result returns `success`, `summary`, and `data` containing `project_dir`, `revision`, `dirty_slides`, relevant paths, issues, and `next_actions`. `finalize` refuses delivery unless strict compile and validation gates pass.

- [ ] **Step 4: Run operation tests**

Mock Node and validation boundaries; test create→edit→render→compile→validate→finalize, stale edit, unsupported operation, strict compile failure, and validation failure. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt/tool.py backend/tests/tools/office/editable_ppt/test_tool.py
git commit -m "feat: expose editable ppt agent tool"
```

### Task 10: Register the new scenario and source-first workflow guide

**Files:**
- Create: `backend/app/tools/office/editable_ppt/references/index.md`
- Create: `backend/app/tools/office/editable_ppt/references/workflow.md`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Modify: `backend/app/agent/skill_metadata.py`
- Modify: `backend/app/tools/office/office_skills_guide.md`
- Modify: `backend/tests/test_assistant_ppt_tool_exposure.py`
- Create: `backend/tests/tools/office/editable_ppt/test_registration.py`

- [ ] **Step 1: Write failing registry and guide tests**

```python
def test_editable_ppt_tool_is_registered_and_exposed():
    registry = create_global_tool_registry()
    assert registry.get_tool("manage_editable_ppt") is not None
    assert "manage_editable_ppt" in ASSISTANT_TOOL_NAMES

def test_editable_ppt_skill_declares_direct_edit_tools():
    metadata = SKILL_METADATA["editable_ppt_generation"]
    assert {"manage_editable_ppt", "read_file", "edit_file"} <= set(metadata["required_tools"])
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt/test_registration.py tests/test_assistant_ppt_tool_exposure.py
```

Expected: new tool and scenario are absent.

- [ ] **Step 3: Register tool and publish progressive guidance**

Register at the next available Office priority, expose it beside the old tool, and add `editable_ppt_generation` metadata. The guide must route high-quality from-scratch requests to the new tool; preserve PPT Master for compatibility; require complete outline, three anchor slides, 3–5 page batches, direct source edits for structural changes, Patch for small changes, strict compile reports, and final validation.

- [ ] **Step 4: Run registry and schema budget regressions**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt/test_registration.py tests/test_assistant_ppt_tool_exposure.py tests/test_assistant_schema_budget.py app/agent/prompts/session_resource_tool_registry_test.py
```

Expected: all pass; existing PPT Master remains exposed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/app/agent/skill_metadata.py backend/app/tools/office/office_skills_guide.md backend/app/tools/office/editable_ppt/references backend/tests
git commit -m "feat: register editable ppt generation scenario"
```

### Task 11: Merge strict compile and existing PPTX QA gates

**Files:**
- Create: `backend/app/tools/office/editable_ppt/quality.py`
- Create: `backend/app/tools/office/editable_ppt/visual_compare.py`
- Create: `backend/tests/tools/office/editable_ppt/test_quality.py`
- Create: `backend/tests/tools/office/editable_ppt/test_visual_compare.py`
- Modify: `backend/app/tools/office/editable_ppt/tool.py`

- [ ] **Step 1: Write failing quality gate tests**

```python
def test_gate_blocks_forbidden_raster_even_when_visual_qa_passes():
    result = build_editable_ppt_gate(
        compile_report={"forbiddenRasterFallbacks": 1, "issues": []},
        validation={"gate": {"status": "passed", "passed": True}, "issues": []},
    )
    assert result.status == "needs_revision"
    assert result.blocking is True
    assert result.issues[0]["code"] == "FORBIDDEN_RASTER_FALLBACK"

def test_visual_compare_reports_missing_and_shifted_critical_elements(tmp_path):
    result = compare_slide_renders(
        html_png=fixture_path("html-slide.png"),
        pptx_png=fixture_path("pptx-slide-shifted.png"),
        html_elements=[{"id": "title", "box": [80, 60, 800, 70], "critical": True}],
        pptx_elements=[{"id": "title", "box": [88, 60, 800, 70], "critical": True}],
        geometry_tolerance_px=4,
    )
    assert result.issues[0]["code"] == "CRITICAL_ELEMENT_GEOMETRY_DRIFT"
```

- [ ] **Step 2: Run and verify RED**

Run `pytest -q tests/tools/office/editable_ppt/test_quality.py tests/tools/office/editable_ppt/test_visual_compare.py`. Expected: missing quality and visual comparison modules.

- [ ] **Step 3: Implement one merged gate**

Normalize compile, HTML runtime, visual comparison, and existing `validate_pptx` issues into `code`, `slide_id`, `element_id`, `severity`, `message`, `evidence`, and `suggestion`. `visual_compare.py` matches critical elements by stable ID, blocks missing elements and geometry drift above 4px, and computes a perceptual page-difference score used only as a warning so antialiasing differences do not fail the deck. Status is `passed`, `needs_revision`, or `qa_failed`. Strict raster fallback, missing native references, corrupt OOXML, blank slides, missing assets, critical geometry drift, and PowerPoint repair risk are blocking.

- [ ] **Step 4: Verify finalize behavior**

Test passed, needs-revision, and QA-unavailable cases; assert `finalize` attaches PPTX only on passed gate and always returns preview/report paths for repair. Run focused tests; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt/quality.py backend/app/tools/office/editable_ppt/visual_compare.py backend/app/tools/office/editable_ppt/tool.py backend/tests/tools/office/editable_ppt/test_quality.py backend/tests/tools/office/editable_ppt/test_visual_compare.py
git commit -m "feat: enforce editable ppt quality gate"
```

### Task 12: Representative themes, layouts, and ten-slide acceptance deck

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/themes/government.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/themes/business.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/themes/data-analysis.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/cover-hero.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/agenda-list.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/section-break.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/text-two-column.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/card-grid.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/kpi-strip.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/chart-right.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/chart-left.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/table-focus.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/process-flow.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/timeline.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/comparison.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/image-story.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/quote.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/layouts/ending.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/deck.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/theme.json`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-001.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-002.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-003.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-004.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-005.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-006.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-007.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-008.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-009.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/fixtures/representative/slides/slide-010.js`
- Create: `backend/app/tools/office/editable_ppt_runtime/test/representative.test.mjs`

- [ ] **Step 1: Write acceptance assertions before fixtures**

Assert the representative deck contains cover, agenda, government content, KPI, native table, combo chart, process diagram, timeline, image page, and ending; strict compile reports zero forbidden fallbacks; expected native counts are present; screenshots exist for all ten pages; and every slide has unique stable IDs.

- [ ] **Step 2: Run and verify RED**

Run `npm test -- --test-name-pattern=representative`. Expected: missing fixtures.

- [ ] **Step 3: Add three themes and first 15 layouts**

Keep theme tokens identical across CSS and PPTX use: canvas, primary, secondary, accent, text, muted, surface, line, title font, body font, title sizes, body sizes, spacing, and corner radius. Layouts are reusable SlideSpec-producing functions; do not multiply layouts by theme.

- [ ] **Step 4: Build the representative source deck and verify native objects**

Create the ten source slides, use local fixture images only, compile, unzip with JSZip, and assert chart XML, embedded workbook, table XML, connectors, stable object names, and no page-sized raster. Run the complete Node suite; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt_runtime/fixtures backend/app/tools/office/editable_ppt_runtime/test/representative.test.mjs
git commit -m "test: add editable ppt acceptance deck"
```

### Task 13: End-to-end Python acceptance and incremental editing proof

**Files:**
- Create: `backend/tests/tools/office/editable_ppt/test_e2e.py`
- Create: `backend/tests/tools/office/editable_ppt/test_incremental_compile.py`

- [ ] **Step 1: Write the end-to-end tests**

Mark browser/LibreOffice-dependent tests with `integration`, `browser`, and `slow`. The normal acceptance test invokes create, copies the representative sources into the created project, renders, compiles, validates, and finalizes. The incremental test records measurement cache hashes, directly edits slide 3, recompiles, and asserts only slide 3's measurement cache changed while source hashes for other slides remain identical.

- [ ] **Step 2: Run unit-mode E2E with mocked external renderer and verify RED**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt/test_e2e.py tests/tools/office/editable_ppt/test_incremental_compile.py -m "not slow"
```

Expected: failure until orchestration exposes all required report fields.

- [ ] **Step 3: Make the minimal orchestration fixes**

Add only missing result fields or cache invalidation wiring discovered by the tests. Do not add existing-PPTX editing or new slide types.

- [ ] **Step 4: Run real browser and LibreOffice acceptance**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt/test_e2e.py tests/tools/office/editable_ppt/test_incremental_compile.py -m "integration or browser"
```

Expected: ten-page PPTX compiles, validates without structural corruption, produces ten PNG previews and montage, and the strict gate passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/office/editable_ppt backend/tests/tools/office/editable_ppt
git commit -m "test: verify editable ppt generation end to end"
```

### Task 14: Twenty/fifty-slide performance and final regression

**Files:**
- Create: `backend/app/tools/office/editable_ppt_runtime/test/performance.test.mjs`
- Create: `backend/tests/tools/office/editable_ppt/test_performance_contract.py`
- Modify: `backend/app/tools/office/editable_ppt/references/workflow.md`

- [ ] **Step 1: Add deterministic 20/50-slide fixture expansion**

Generate expanded projects in the test temp directory by repeating validated layout functions with unique IDs and data; do not commit 50 hand-written source files. Record cold and warm compile timings, peak RSS, cache hits, and output size in the compile report.

- [ ] **Step 2: Run the performance test and record baseline**

Run:

```bash
cd backend/app/tools/office/editable_ppt_runtime
npm test -- --test-name-pattern=performance
```

Expected: both decks compile successfully; the first run may fail the target until cache and browser reuse are applied.

- [ ] **Step 3: Apply bounded performance fixes**

Reuse one browser, cache theme/assets/unchanged DOM measurements by SHA-256, compile only dirty previews, cap concurrent image decoding, and emit a warning rather than hiding measurements when the target server exceeds 30 seconds for 10 pages or 120 seconds for 50 pages.

- [ ] **Step 4: Run complete regressions**

Run:

```bash
cd backend/app/tools/office/editable_ppt_runtime
npm test
```

Then:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/office/editable_ppt tests/test_assistant_ppt_tool_exposure.py tests/test_assistant_schema_budget.py app/agent/prompts/session_resource_tool_registry_test.py
```

Expected: all Node and focused Python tests pass. Performance reports identify whether target timings pass on the current host; timing warnings alone do not override structural or editability gates.

- [ ] **Step 5: Update workflow evidence and commit**

Document the verified commands, supported CSS subset, strict fallback rules, direct-edit workflow, cache behavior, and measured host baseline in the workflow guide.

```bash
git add backend/app/tools/office/editable_ppt_runtime/test/performance.test.mjs backend/tests/tools/office/editable_ppt/test_performance_contract.py backend/app/tools/office/editable_ppt/references/workflow.md
git commit -m "perf: validate editable ppt long decks"
```

### Task 15: Final verification and handoff

**Files:**
- Modify only if verification finds a scoped defect in files already listed above.

- [ ] **Step 1: Verify repository diff scope**

Run `git status --short` and `git diff --stat origin/main...HEAD`. Expected: only editable PPT runtime/service, focused registrations/guides/tests, package locks, and the approved docs are changed.

- [ ] **Step 2: Run final Node verification**

Run `npm test` in `backend/app/tools/office/editable_ppt_runtime`. Expected: PASS.

- [ ] **Step 3: Run final Python verification**

Run the focused Python command from Task 14. Expected: PASS.

- [ ] **Step 4: Inspect one real deliverable**

Open the generated ZIP structure programmatically, confirm ten slides, chart workbook, table objects, connectors, no forbidden raster fallback, compile report, validation report, screenshots, and montage. If Microsoft PowerPoint is available, open the file and confirm no repair prompt plus editable chart data; otherwise record that manual PowerPoint verification remains environment-dependent and do not claim it was performed.

- [ ] **Step 5: Prepare completion summary**

Report implemented scope, exact verification commands/results, representative output paths, performance baseline, known CSS limitations, and the explicit phase-two boundary for existing PPTX editing.
