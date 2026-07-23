import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { analyzeBounds, assetReferenceIssues, measureDeck, runtimeDiagnosticIssues } from "../src/measure.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PROJECT = path.join(HERE, "fixtures", "project");

test("bounds analysis reports elements outside the fixed slide", () => {
  assert.deepEqual(
    analyzeBounds({ id: "risk-card", box: { x: 1400, y: 760, width: 100, height: 80 } }),
    [
      {
        code: "ELEMENT_OUT_OF_BOUNDS",
        elementId: "risk-card",
        message: "element exceeds 1440x810 slide bounds",
        box: { x: 1400, y: 760, width: 100, height: 80 },
      },
    ],
  );
});

test("runtime diagnostics reject missing CSS, Vite overlays, and browser errors", () => {
  assert.deepEqual(
    runtimeDiagnosticIssues({
      cssReady: false,
      viteError: "Cannot resolve tailwindcss",
      browserErrors: ["stylesheet request failed"],
    }).map((issue) => issue.code),
    ["RUNTIME_CSS_NOT_READY", "RUNTIME_BUILD_FAILED", "BROWSER_RUNTIME_ERROR"],
  );
});

test("asset references must use the portable project assets directory", () => {
  const issues = assetReferenceIssues([
    { id: "managed", tagName: "img", src: "./assets/chart.png" },
    { id: "external", tagName: "img", src: "/home/user/chart.png" },
    { id: "wrong-dir", tagName: "img", src: "./images/chart.png" },
  ]);
  assert.deepEqual(issues.map((issue) => issue.elementId), ["external", "wrong-dir"]);
  assert.equal(issues.every((issue) => issue.code === "ASSET_REFERENCE_OUTSIDE_PROJECT"), true);
});

test("measures a 1440x810 slide and writes its screenshot", { timeout: 45_000 }, async () => {
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-measure-"));
  const result = await measureDeck(FIXTURE_PROJECT, outputDir, { pages: [1] });
  assert.deepEqual(result.viewport, { width: 1440, height: 810 });
  assert.equal(result.pages.length, 1);
  assert.equal(result.pages[0].slideId, "cover");
  assert.equal(result.pages[0].elements.some((item) => item.id === "title"), true);
  const slideRoot = result.pages[0].elements.find((item) => item.id === "slide-root");
  assert.equal(slideRoot.box.width, 1440, "Tailwind w-[1440px] must be compiled in the materialized runtime");
  assert.equal(slideRoot.box.height, 810, "Tailwind h-[810px] must be compiled in the materialized runtime");
  assert.equal(result.pages[0].diagnostics.cssReady, true);
  assert.equal((await fs.stat(result.pages[0].screenshotPath)).size > 0, true);
  assert.deepEqual(result.pages[0].issues, []);
});

test("reuses unchanged slide measurements from the persistent cache", { timeout: 45_000 }, async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-cache-"));
  const cacheDir = path.join(root, "cache");
  const first = await measureDeck(FIXTURE_PROJECT, path.join(root, "first"), { cacheDir, dirtySlides: ["cover"] });
  const second = await measureDeck(FIXTURE_PROJECT, path.join(root, "second"), { cacheDir, dirtySlides: [] });
  assert.equal(first.pages[0].cacheHit, false);
  assert.equal(second.pages[0].cacheHit, true);
  assert.equal(second.cache.hits, 1);
  assert.equal(second.cache.misses, 0);
  assert.equal((await fs.stat(second.pages[0].screenshotPath)).size > 0, true);
});
