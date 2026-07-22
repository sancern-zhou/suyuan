import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { analyzeBounds, measureDeck } from "../src/measure.mjs";

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

test("measures a 1440x810 slide and writes its screenshot", { timeout: 45_000 }, async () => {
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-measure-"));
  const result = await measureDeck(FIXTURE_PROJECT, outputDir, { pages: [1] });
  assert.deepEqual(result.viewport, { width: 1440, height: 810 });
  assert.equal(result.pages.length, 1);
  assert.equal(result.pages[0].slideId, "cover");
  assert.equal(result.pages[0].elements.some((item) => item.id === "title"), true);
  assert.equal((await fs.stat(result.pages[0].screenshotPath)).size > 0, true);
  assert.deepEqual(result.pages[0].issues, []);
});
