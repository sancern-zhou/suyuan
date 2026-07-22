import test from "node:test";
import assert from "node:assert/strict";

import { addBasicElement, normalizeColor, pxBoxToInches } from "../src/pptx/basic_adapter.mjs";
import { addNativeElement } from "../src/pptx/semantic_adapter.mjs";
import { assertEditable, auditFallbacks } from "../src/pptx/strict_policy.mjs";

function fakeSlideRecorder() {
  const calls = [];
  return {
    calls,
    addText(text, options) { calls.push({ method: "addText", text, options }); },
    addShape(shape, options) { calls.push({ method: "addShape", shape, options }); },
    addImage(options) { calls.push({ method: "addImage", options }); },
    addTable(rows, options) { calls.push({ method: "addTable", rows, options }); },
    addChart(type, data, options) { calls.push({ method: "addChart", type, data, options }); },
  };
}

const pptxApi = {
  ChartType: { bar: "bar", column: "column", line: "line", pie: "pie", doughnut: "doughnut" },
  ShapeType: { rect: "rect", roundRect: "roundRect", line: "line" },
};

test("strict mode rejects rasterized text and allows source photos", () => {
  assert.throws(
    () => assertEditable({ kind: "text", fallback: "png", id: "title" }, "strict"),
    (error) => error.code === "RASTER_FALLBACK_FORBIDDEN" && error.elementId === "title",
  );
  assert.doesNotThrow(() =>
    assertEditable({ kind: "image", fallback: "png", assetKind: "user-photo", id: "photo" }, "strict"),
  );
});

test("fallback audit counts forbidden and allowed raster objects", () => {
  assert.deepEqual(
    auditFallbacks(
      [
        { kind: "text", fallback: "png", id: "title" },
        { kind: "image", fallback: "png", assetKind: "generated-image", id: "hero" },
      ],
      "strict",
    ),
    { allowedRasterFallbacks: 1, forbiddenRasterFallbacks: 1, forbiddenElementIds: ["title"] },
  );
});

test("basic adapter maps measured text to editable text with normalized colors", () => {
  const slide = fakeSlideRecorder();
  addBasicElement(
    slide,
    {
      id: "title",
      source: "dom",
      tagName: "h1",
      text: "年度报告",
      box: { x: 108, y: 81, width: 540, height: 108 },
      style: {
        color: "rgb(31, 41, 55)",
        backgroundColor: "rgba(0, 0, 0, 0)",
        fontFamily: '"Microsoft YaHei", sans-serif',
        fontSize: "48px",
        fontWeight: "700",
        textAlign: "left",
        opacity: "1",
      },
    },
    { ShapeType: pptxApi.ShapeType },
  );
  assert.equal(slide.calls[0].method, "addText");
  assert.equal(slide.calls[0].options.color, "1F2937");
  assert.equal(slide.calls[0].options.fontFace, "Microsoft YaHei");
  const inches = pxBoxToInches({ x: 108, y: 81, width: 540, height: 108 });
  assert.equal(Math.abs(inches.x - 1) < 0.001, true);
  assert.equal(Math.abs(inches.y - 0.75) < 0.001, true);
  assert.equal(Math.abs(inches.w - 5) < 0.001, true);
  assert.equal(Math.abs(inches.h - 1) < 0.001, true);
  assert.equal(normalizeColor("#174A7C"), "174A7C");
});

test("semantic adapters emit native chart and table calls", () => {
  const slide = fakeSlideRecorder();
  const theme = { primary: "174A7C", text: "1F2937", fontBody: "Microsoft YaHei" };
  const box = { x: 108, y: 108, width: 648, height: 432 };
  addNativeElement(
    slide,
    {
      id: "chart-1",
      kind: "chart",
      chartType: "column",
      data: { categories: ["2025", "2026"], series: [{ name: "收入", values: [10, 15] }] },
    },
    box,
    theme,
    pptxApi,
  );
  addNativeElement(
    slide,
    {
      id: "table-1",
      kind: "table",
      data: { rows: [["指标", "数值"], ["收入", "15"]] },
    },
    box,
    theme,
    pptxApi,
  );
  assert.deepEqual(slide.calls.map((call) => call.method), ["addChart", "addTable"]);
  assert.deepEqual(slide.calls[0].data, [{ name: "收入", labels: ["2025", "2026"], values: [10, 15] }]);
  assert.equal(slide.calls[0].options.showLegend, true);
  assert.equal(slide.calls[0].options.barDir, "col");
});

test("diagram adapter emits separately editable nodes and connectors", () => {
  const slide = fakeSlideRecorder();
  addNativeElement(
    slide,
    {
      id: "process-1",
      kind: "diagram",
      data: {
        nodes: [{ id: "start", label: "开始" }, { id: "finish", label: "完成" }],
        edges: [{ id: "edge-1", source: "start", target: "finish" }],
      },
    },
    { x: 108, y: 216, width: 1080, height: 270 },
    { primary: "174A7C", text: "1F2937", fontBody: "Microsoft YaHei" },
    pptxApi,
  );
  assert.deepEqual(slide.calls.map((call) => call.method), ["addShape", "addText", "addShape", "addText", "addShape"]);
  assert.equal(slide.calls.at(-1).shape, "line");
  assert.equal(slide.calls.at(-1).options.objectName, "edge-1");
});
