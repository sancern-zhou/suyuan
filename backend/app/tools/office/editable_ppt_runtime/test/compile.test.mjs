import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import JSZip from "jszip";

import { compileDeck } from "../src/compile.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PROJECT = path.join(HERE, "fixtures", "project");
const CLI_PATH = path.resolve(HERE, "..", "src", "cli.mjs");

const NATIVE_SLIDE = `window.slideDataMap.set(1, {
  schemaVersion: "1.0",
  id: "cover",
  type: "data-analysis",
  intent: "show native objects",
  layoutMode: "freeform",
  html: \`<section class="relative w-[1440px] h-[810px]" data-pptx-id="slide-root">
    <h1 class="absolute left-[80px] top-[50px] text-[42px]" data-pptx-id="title">年度报告</h1>
    <div class="absolute left-[80px] top-[160px] w-[700px] h-[420px]" data-pptx-ref="chart-1"></div>
    <div class="absolute left-[820px] top-[160px] w-[520px] h-[420px]" data-pptx-ref="table-1"></div>
  </section>\`,
  nativeElements: [
    {
      id: "chart-1",
      kind: "chart",
      chartType: "column",
      data: { categories: ["2025", "2026"], series: [{ name: "收入", values: [10, 15] }] }
    },
    {
      id: "table-1",
      kind: "table",
      data: { rows: [["指标", "数值"], ["收入", "15"]] }
    }
  ],
  speakerNotes: []
});
`;

async function nativeProject() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-compile-project-"));
  await fs.cp(FIXTURE_PROJECT, root, { recursive: true });
  await fs.writeFile(path.join(root, "slides", "slide-001.js"), NATIVE_SLIDE, "utf8");
  return root;
}

test("compile writes pptx and strict compile report", { timeout: 45_000 }, async () => {
  const projectDir = await nativeProject();
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-compile-output-"));
  const result = await compileDeck(projectDir, outputDir, { editable: "strict" });
  assert.equal(result.success, true);
  assert.equal((await fs.stat(result.pptxPath)).size > 0, true);
  assert.equal(result.report.forbiddenRasterFallbacks, 0);
  assert.equal(result.report.native.chart, 1);
  assert.equal(result.report.native.table, 1);
  assert.equal(result.report.slideCount, 1);

  const zip = await JSZip.loadAsync(await fs.readFile(result.pptxPath));
  assert.equal(Object.keys(zip.files).some((name) => /^ppt\/charts\/chart\d+\.xml$/.test(name)), true);
  assert.equal(Object.keys(zip.files).some((name) => /^ppt\/embeddings\/.+\.xlsx$/.test(name)), true);
});

test("CLI health command returns one JSON object", () => {
  const run = spawnSync(process.execPath, [CLI_PATH], {
    input: '{"command":"health"}\n',
    encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stderr);
  assert.deepEqual(JSON.parse(run.stdout), { success: true, runtime: "editable-ppt", schemaVersion: "1.0" });
});

test("CLI rejects malformed JSON without writing protocol noise to stdout", () => {
  const run = spawnSync(process.execPath, [CLI_PATH], { input: "not-json\n", encoding: "utf8" });
  assert.equal(run.status, 1);
  assert.equal(run.stdout, "");
  assert.match(run.stderr, /COMPILER_PROTOCOL_ERROR/);
});

test("compile rejects output file names containing a directory", async () => {
  const projectDir = await nativeProject();
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-output-name-"));
  await assert.rejects(
    () => compileDeck(projectDir, outputDir, { fileName: "../outside.pptx" }),
    /OUTPUT_FILE_NAME_INVALID/,
  );
});
