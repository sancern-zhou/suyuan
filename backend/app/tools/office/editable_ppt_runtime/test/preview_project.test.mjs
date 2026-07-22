import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { materializePreview } from "../src/preview_project.mjs";
import { pageFromSearch, stepPage } from "../runtime/controller.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PROJECT = path.join(HERE, "fixtures", "project");

test("materializes immutable runtime with project data and Tailwind source", async () => {
  const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "editable-ppt-preview-"));
  const outputDir = path.join(tempRoot, "runtime");
  const result = await materializePreview(FIXTURE_PROJECT, outputDir);

  assert.equal(result.outputDir, outputDir);
  assert.equal(await fs.readFile(path.join(outputDir, "index.html"), "utf8").then(Boolean), true);
  const css = await fs.readFile(path.join(outputDir, "input.css"), "utf8");
  assert.match(css, /@import "tailwindcss"/);
  assert.match(css, /@source ".*test\/fixtures\/project\/slides"/);
  const payload = JSON.parse(await fs.readFile(path.join(outputDir, "deck-runtime.json"), "utf8"));
  assert.equal(payload.slides.length, 1);
  assert.equal(payload.slides[0].id, "cover");
  assert.equal(payload.theme.id, "government");
  assert.equal((await fs.stat(path.join(outputDir, "assets", "pixel.svg"))).isFile(), true);
});

test("preview route defaults to page one and rejects invalid deep links", () => {
  assert.equal(pageFromSearch("", 3), 1);
  assert.equal(pageFromSearch("?page=2", 3), 2);
  assert.throws(() => pageFromSearch("?page=0", 3), /page must be between 1 and 3/);
  assert.throws(() => pageFromSearch("?page=word", 3), /page must be an integer/);
});

test("keyboard page stepping remains inside deck bounds", () => {
  assert.equal(stepPage(1, -1, 3), 1);
  assert.equal(stepPage(1, 1, 3), 2);
  assert.equal(stepPage(3, 1, 3), 3);
});
