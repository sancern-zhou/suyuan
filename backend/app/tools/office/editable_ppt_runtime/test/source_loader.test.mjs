import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadProject, loadSlideSource, resolveInside } from "../src/source_loader.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PROJECT = path.join(HERE, "fixtures", "project");

test("loads slideDataMap registrations in numeric order", async () => {
  const project = await loadProject(FIXTURE_PROJECT);
  assert.equal(project.slides.length, 1);
  assert.equal(project.slides[0].number, 1);
  assert.equal(project.slides[0].id, "cover");
  assert.equal(project.slides[0].html.includes("年度报告"), true);
  assert.equal(project.theme.id, "government");
});

test("slide source cannot access process or require", () => {
  assert.throws(
    () => loadSlideSource('process.exit(1); window.slideDataMap.set(1, {});', "malicious.js"),
    /process is not defined/,
  );
  assert.throws(
    () => loadSlideSource('require("node:fs"); window.slideDataMap.set(1, {});', "malicious.js"),
    /require is not defined/,
  );
});

test("slide source cannot escape through a host Map constructor", () => {
  assert.throws(
    () => loadSlideSource('window.slideDataMap.constructor.constructor("return process")()'),
    /Code generation from strings disallowed|process is not defined/,
  );
});

test("slide getters are serialized inside the VM timeout", () => {
  assert.throws(
    () => loadSlideSource('window.slideDataMap.set(1, { get schemaVersion() { while (true) {} } });'),
    /timed out/,
  );
});

test("slide source must register exactly one positive integer page", () => {
  assert.throws(() => loadSlideSource("void 0;", "empty.js"), /must register exactly one slide/);
  assert.throws(
    () => loadSlideSource('window.slideDataMap.set("one", {});', "string-page.js"),
    /positive integer page number/,
  );
});

test("resolved project paths cannot escape the project root", () => {
  assert.throws(() => resolveInside(FIXTURE_PROJECT, "../secret.json"), /outside project root/);
  assert.equal(resolveInside(FIXTURE_PROJECT, "theme.json"), path.join(FIXTURE_PROJECT, "theme.json"));
});
