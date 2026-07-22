import test from "node:test";
import assert from "node:assert/strict";

import { validateDeck, validateSlide } from "../src/contracts.mjs";

test("deck requires schema version, stable id, theme, and ordered slides", () => {
  assert.deepEqual(validateDeck({}), {
    ok: false,
    errors: [
      "schemaVersion is required",
      "id is required",
      "theme is required",
      "slides must be a non-empty array",
    ],
  });
});

test("deck rejects unsupported schema and duplicate slide references", () => {
  const result = validateDeck({
    schemaVersion: "2.0",
    id: "annual-report",
    theme: "government",
    slides: ["cover", "cover"],
  });
  assert.equal(result.ok, false);
  assert.deepEqual(result.errors, [
    "schemaVersion must be 1.0",
    "slides must contain unique stable ids",
  ]);
});

test("slide accepts HTML plus native chart data with stable ids", () => {
  const result = validateSlide({
    schemaVersion: "1.0",
    id: "growth",
    type: "data-analysis",
    intent: "show growth",
    layoutMode: "freeform",
    html: '<section><div data-pptx-ref="chart-1"></div></section>',
    nativeElements: [
      {
        id: "chart-1",
        kind: "chart",
        chartType: "column",
        data: {
          categories: ["2025"],
          series: [{ name: "收入", values: [10] }],
        },
      },
    ],
    speakerNotes: [],
  });
  assert.deepEqual(result, { ok: true, errors: [] });
});

test("slide rejects duplicate native ids and missing placeholders", () => {
  const result = validateSlide({
    schemaVersion: "1.0",
    id: "growth",
    type: "data-analysis",
    intent: "show growth",
    layoutMode: "freeform",
    html: "<section></section>",
    nativeElements: [
      { id: "chart-1", kind: "chart", chartType: "column", data: { categories: [], series: [] } },
      { id: "chart-1", kind: "table", data: { rows: [] } },
    ],
    speakerNotes: [],
  });
  assert.equal(result.ok, false);
  assert.deepEqual(result.errors, [
    "nativeElements must contain unique stable ids",
    "native element chart-1 is missing data-pptx-ref placeholder",
  ]);
});

test("chart series values must match category count", () => {
  const result = validateSlide({
    schemaVersion: "1.0",
    id: "growth",
    type: "data-analysis",
    intent: "show growth",
    layoutMode: "freeform",
    html: '<div data-pptx-ref="chart-1"></div>',
    nativeElements: [
      {
        id: "chart-1",
        kind: "chart",
        chartType: "column",
        data: { categories: ["2025", "2026"], series: [{ name: "收入", values: [10] }] },
      },
    ],
    speakerNotes: [],
  });
  assert.deepEqual(result.errors, ["chart chart-1 series 收入 values must match categories"]);
});
