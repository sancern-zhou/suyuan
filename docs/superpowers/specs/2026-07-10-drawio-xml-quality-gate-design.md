# Draw.io XML Quality Gate Design

## Goal

Improve AI-generated interactive draw.io boards by adding a deterministic XML quality gate and tightening the chart-mode drawing guidance. Multi-page preservation and frontend export changes are explicitly out of scope.

## Scope

This change applies only to `create_drawio_board` and its chart-mode guidance.

Included:

- structural validation that rejects XML which cannot be edited or rendered reliably;
- non-blocking quality diagnostics for likely visual defects;
- structured quality results returned by the tool so the Agent can revise a board;
- progressive, task-specific draw.io guidance and a concise pre-delivery checklist;
- focused unit tests for validation, diagnostics, and tool result contracts.

Excluded:

- preserving or editing multiple `<diagram>` pages;
- changing the embedded diagrams.net frontend;
- server-side PNG, SVG, or PDF export;
- automatic graph layout or pixel-level visual inspection;
- changes to `create_diagram_artifact`.

## Chosen Approach

Use a two-level gate inside the existing XML normalization path.

1. **Errors block the tool call.** These cover deterministic contract violations: duplicate or missing IDs, invalid parent/source/target references, missing vertex geometry, invalid edge geometry, and unsafe HTML-like labels.
2. **Warnings do not block the tool call.** These cover useful but heuristic checks: overlapping top-level vertices, missing wrap/plain-text style settings, overly long labels, and excessively verbose edge labels.

This keeps the gate useful without making hand-drawn or intentionally unusual boards impossible to save. It also avoids adding a layout engine or frontend dependency.

## Architecture

### Quality report

Add a focused quality module beside `xml_utils.py`. It accepts normalized cells and returns a serializable report:

```json
{
  "status": "pass | warning | error",
  "errors": [{"code": "...", "cell_id": "...", "message": "..."}],
  "warnings": [{"code": "...", "cell_id": "...", "message": "..."}],
  "metrics": {"cell_count": 0, "vertex_count": 0, "edge_count": 0}
}
```

Issue codes are stable machine-readable identifiers. Messages are concise Chinese descriptions suitable for an Agent repair loop.

### Normalization flow

`normalize_drawio_xml` and `apply_drawio_operations` continue to own parsing and serialization. Their existing structural validation is strengthened where the result is unquestionably invalid. After normalization or editing, the quality module evaluates the final cell set.

The tool blocks on quality errors by converting them to the existing `DrawioXmlError` failure path. Warnings are attached to successful results and do not alter XML.

### Tool result contract

Successful `create_drawio_board` results add `data.quality_report`. The summary mentions the warning count when warnings exist, prompting the Agent to revise instead of treating the first render as final. Failed calls retain the current failure shape and add structured quality details when available.

No frontend change is required because additional result fields are backward compatible.

## Gate Rules

### Blocking errors

- every non-root `mxCell` has a unique ID;
- every declared `parent`, `source`, and `target` points to an existing cell or root cell;
- every vertex has `mxGeometry` with finite `x`, `y`, `width`, and `height`;
- vertex width and height are positive;
- every edge has `mxGeometry relative="1"`;
- labels do not contain raw or escaped HTML tags such as `<br>`, `<b>`, `&lt;br&gt;`, or `&lt;b&gt;`.

### Non-blocking warnings

- top-level vertex rectangles overlap materially;
- a regular node lacks `whiteSpace=wrap`;
- a generated node does not use `html=0`;
- a node label is too long for a concise diagram node;
- an edge label is longer than a short relationship/action label.

Overlap detection ignores edges, text-only title/annotation nodes, containers, and parent-child pairs. It uses geometry only and is intentionally advisory.

## Skill Guidance Changes

The chart-mode guidance will be organized as progressive disclosure:

- `drawio_board_workflow.md` remains the router and mandatory workflow;
- `drawio_xml_rules.md` defines the hard XML contract and aligns examples with `html=0` and plain-text values;
- a new `drawio_quality_checklist.md` defines preflight and repair-loop checks;
- existing pattern files remain task-specific references and are loaded only when relevant.

The workflow will require the Agent to:

1. determine diagram type and reading direction before producing XML;
2. build stable semantic IDs and a simple layout outline;
3. call the tool;
4. inspect `quality_report`;
5. revise warnings that materially affect readability before final delivery.

The guidance will explicitly prefer pure text in `mxCell.value`, short edge labels, semantic colors, orthogonal connectors, and local edits for existing boards.

## Error Handling

Parsing and gate failures use the existing unsuccessful tool response rather than raising through the runtime. The response identifies the issue code and affected cell where possible. Edit operations are applied to a copy, so a rejected edit never replaces the current board state or stores an invalid version.

Warnings never prevent persistence. This is important for hand-edited diagrams and uncommon but valid layouts.

## Testing

Focused tests will cover:

- missing or invalid geometry is rejected;
- dangling parent references are rejected in addition to dangling edges;
- HTML-like values are rejected while XML newline entities remain valid;
- overlapping nodes and long labels produce warnings without failure;
- title/annotation and nested container geometry do not create false overlap warnings;
- successful tool results include the quality report;
- warning summaries encourage a repair loop;
- existing create/edit and persistence behavior remains green.

Tests run in the project environment with:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/app/tools/visualization/create_drawio_board/xml_utils_test.py \
  backend/app/tools/visualization/create_drawio_board/tool_test.py -q
```

## Success Criteria

- structurally broken or HTML-contaminated draw.io XML cannot be persisted by the tool;
- likely readability defects are visible to the Agent as stable structured warnings;
- current single-page create/edit flows and frontend rendering contracts remain compatible;
- the chart-mode instructions describe a design, generate, inspect, revise workflow without loading every pattern document.
