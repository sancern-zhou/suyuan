import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import JSZip from "jszip";
import { compileDeck } from "../src/compile.mjs";
import { loadProject } from "../src/source_loader.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "..", "fixtures");

test("representative ten-slide deck compiles with native semantic objects", { timeout: 60_000 }, async () => {
  const projectDir = path.join(FIXTURES, "representative");
  const project = await loadProject(projectDir);
  assert.equal(project.slides.length, 10);
  assert.equal(new Set(project.slides.map((slide) => slide.id)).size, 10);
  assert.deepEqual(project.slides.map((slide) => slide.type), [
    "cover", "agenda", "section", "kpi", "data-analysis", "table", "process", "timeline", "image-story", "ending",
  ]);
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-representative-"));
  const result = await compileDeck(projectDir, outputDir, { editable: "strict" });
  assert.equal(result.success, true);
  assert.equal(result.report.slideCount, 10);
  assert.equal(result.report.measurement.screenshots.length, 10);
  assert.equal(result.report.native.chart >= 1, true);
  assert.equal(result.report.native.table >= 1, true);
  assert.equal(result.report.native.diagram >= 1, true);
  assert.equal(result.report.native.image >= 1, true);
  assert.equal(result.report.forbiddenRasterFallbacks, 0);
  const zip = await JSZip.loadAsync(await fs.readFile(result.pptxPath));
  const names = Object.keys(zip.files);
  assert.equal(names.some((name) => /^ppt\/charts\/chart\d+\.xml$/.test(name)), true);
  assert.equal(names.some((name) => /^ppt\/embeddings\/.+\.xlsx$/.test(name)), true);
  for (const screenshot of result.report.measurement.screenshots) assert.equal((await fs.stat(screenshot)).size > 0, true);
});

test("ships three themes and fifteen reusable layout modules", async () => {
  for (const theme of ["government", "business", "data-analysis"]) {
    const value = JSON.parse(await fs.readFile(path.join(FIXTURES, "themes", `${theme}.json`), "utf8"));
    assert.equal(Boolean(value.primary && value.fontTitle && value.spacing && value.cornerRadius), true);
  }
  const layouts = (await fs.readdir(path.join(FIXTURES, "layouts"))).filter((name) => name.endsWith(".js"));
  assert.equal(layouts.length, 15);
});
