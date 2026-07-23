import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import JSZip from "jszip";

import { compileDeck, inspectProject, unsupportedStyleIssues } from "../src/compile.mjs";

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

test("compile preserves an opaque slide-root background as the native slide background", { timeout: 45_000 }, async () => {
  const projectDir = await nativeProject();
  const slidePath = path.join(projectDir, "slides", "slide-001.js");
  const source = await fs.readFile(slidePath, "utf8");
  await fs.writeFile(
    slidePath,
    source.replace(
      'class="relative w-[1440px] h-[810px]" data-pptx-id="slide-root"',
      'class="relative w-[1440px] h-[810px]" style="background: #0A2540" data-pptx-id="slide-root"',
    ),
    "utf8",
  );
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-root-background-"));

  const result = await compileDeck(projectDir, outputDir, { editable: "strict" });

  assert.equal(result.success, true);
  const zip = await JSZip.loadAsync(await fs.readFile(result.pptxPath));
  const slideXml = await zip.file("ppt/slides/slide1.xml").async("string");
  assert.match(slideXml, /<a:srgbClr val="0A2540"/);
});

test("compile preserves mixed inline text as one native rich-text box", { timeout: 45_000 }, async () => {
  const projectDir = await nativeProject();
  const slidePath = path.join(projectDir, "slides", "slide-001.js");
  const source = await fs.readFile(slidePath, "utf8");
  await fs.writeFile(
    slidePath,
    source.replace(
      '<h1 class="absolute left-[80px] top-[50px] text-[42px]" data-pptx-id="title">年度报告</h1>',
      '<p class="absolute left-[80px] top-[50px] text-[24px]" data-pptx-id="summary">前缀<span class="text-[#00B4D8] font-bold" data-pptx-id="summary-accent">强调</span>后缀</p>',
    ),
    "utf8",
  );
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-rich-text-"));

  const result = await compileDeck(projectDir, outputDir, { editable: "strict" });

  assert.equal(result.success, true);
  const zip = await JSZip.loadAsync(await fs.readFile(result.pptxPath));
  const slideXml = await zip.file("ppt/slides/slide1.xml").async("string");
  assert.match(slideXml, /<a:t>前缀<\/a:t>/);
  assert.match(slideXml, /<a:t>强调<\/a:t>/);
  assert.match(slideXml, /<a:t>后缀<\/a:t>/);
  assert.equal((slideXml.match(/name="summary"/g) || []).length, 1);
  assert.equal((slideXml.match(/name="summary-accent"/g) || []).length, 0);
});

test("CLI health command returns one JSON object", () => {
  const run = spawnSync(process.execPath, [CLI_PATH], {
    input: '{"command":"health"}\n',
    encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stderr);
  assert.deepEqual(JSON.parse(run.stdout), { success: true, runtime: "editable-ppt", schemaVersion: "1.0" });
});

test("inspect returns the exact source path for every slide", async () => {
  const result = await inspectProject(FIXTURE_PROJECT);

  assert.deepEqual(result.slideSources, [
    { pageNumber: 1, slideId: "cover", relativePath: "slides/slide-001.js" },
  ]);
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

test("strict style audit discovers unsupported native styling itself", () => {
  const issues = unsupportedStyleIssues({ pages: [{ slideId: "cover", elements: [{ id: "hero", style: { backgroundImage: "linear-gradient(red, blue)", filter: "none", transform: "none", boxShadow: "none" } }] }] });
  assert.equal(issues[0].code, "UNSUPPORTED_STYLE_STRICT");
  assert.equal(issues[0].elementId, "hero");
});

test("strict style audit rejects mixed tagged spans and untagged direct text", () => {
  const issues = unsupportedStyleIssues({
    pages: [{
      slideId: "summary",
      elements: [{
        id: "summary-copy",
        source: "dom",
        style: {},
        hasUntaggedTextDescendant: false,
        hasUntaggedDirectText: true,
      }],
    }],
  });

  assert.equal(issues[0].code, "UNTAGGED_TEXT_STRICT");
  assert.match(issues[0].message, /text-bearing/);
});
