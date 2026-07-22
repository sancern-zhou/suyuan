import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { compileDeck } from "../src/compile.mjs";

async function expandedProject(count) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), `editable-ppt-${count}-`));
  await fs.mkdir(path.join(root, "slides"));
  const ids = Array.from({ length: count }, (_, index) => `page-${index + 1}`);
  await fs.writeFile(path.join(root, "deck.json"), JSON.stringify({ schemaVersion: "1.0", id: `deck-${count}`, theme: "theme.json", slides: ids }));
  await fs.writeFile(path.join(root, "theme.json"), JSON.stringify({ canvas: "#F8FAFC", primary: "#174A7C", text: "#1F2937", fontTitle: "Arial", fontBody: "Arial" }));
  await Promise.all(ids.map((id, index) => fs.writeFile(
    path.join(root, "slides", `slide-${String(index + 1).padStart(3, "0")}.js`),
    `window.slideDataMap.set(${index + 1},{schemaVersion:"1.0",id:"${id}",type:"content",intent:"performance",layoutMode:"freeform",html:\`<section class="relative w-[1440px] h-[810px] bg-white" data-pptx-id="slide-root"><h1 class="absolute left-[80px] top-[80px] text-[38px]" data-pptx-id="title">Page ${index + 1}</h1><p class="absolute left-[80px] top-[180px] text-[22px]" data-pptx-id="body">Deterministic performance fixture</p></section>\`,nativeElements:[],speakerNotes:[]});\n`,
  )));
  return root;
}

test("20/50 slide cold and warm compile performance contract", { timeout: 240_000, skip: process.env.EDITABLE_PPT_PERFORMANCE !== "1" }, async () => {
  for (const count of [20, 50]) {
    const project = await expandedProject(count);
    const output = await fs.mkdtemp(path.join(os.tmpdir(), `editable-ppt-${count}-out-`));
    const cacheDir = path.join(output, "cache");
    const cold = await compileDeck(project, path.join(output, "cold"), { cacheDir, dirtySlides: Array.from({ length: count }, (_, i) => `page-${i + 1}`) });
    const warm = await compileDeck(project, path.join(output, "warm"), { cacheDir, dirtySlides: [] });
    assert.equal(cold.success && warm.success, true);
    assert.deepEqual(cold.report.measurement.cache, { enabled: true, hits: 0, misses: count });
    assert.deepEqual(warm.report.measurement.cache, { enabled: true, hits: count, misses: 0 });
    assert.equal(warm.report.durationMs < cold.report.durationMs, true);
    assert.equal(warm.report.outputSizeBytes > 0, true);
    assert.equal(warm.report.rssBytes > 0, true);
    const targetMs = count === 20 ? 60_000 : 120_000;
    assert.equal(cold.report.durationMs < targetMs, true, `${count} slide cold compile exceeded ${targetMs}ms`);
  }
});
