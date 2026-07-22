import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

import { loadProject } from "./source_loader.mjs";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const RUNTIME_DIR = path.resolve(MODULE_DIR, "..", "runtime");

async function assetHashes(root) {
  const result = {};
  async function visit(dir) {
    let entries;
    try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch (error) { if (error.code === "ENOENT") return; throw error; }
    for (const entry of entries) {
      const current = path.join(dir, entry.name);
      if (entry.isDirectory()) await visit(current);
      if (entry.isFile()) result[path.relative(root, current).replaceAll("\\", "/")] = crypto.createHash("sha256").update(await fs.readFile(current)).digest("hex");
    }
  }
  await visit(root);
  return result;
}

function quoteTailwindSource(sourcePath) {
  return sourcePath.replaceAll("\\", "/").replaceAll('"', '\\"');
}

export async function materializePreview(projectDir, outputDir = path.join(projectDir, ".editable-ppt-runtime")) {
  const project = await loadProject(projectDir);
  const resolvedOutput = path.resolve(outputDir);
  await fs.mkdir(resolvedOutput, { recursive: true });
  await fs.cp(RUNTIME_DIR, resolvedOutput, { recursive: true, force: true });
  const assetsDir = path.join(project.projectRoot, "assets");
  try {
    await fs.cp(assetsDir, path.join(resolvedOutput, "assets"), { recursive: true, force: true });
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }

  const slideSource = quoteTailwindSource(path.join(project.projectRoot, "slides"));
  const cssPath = path.join(resolvedOutput, "input.css");
  const baseCss = await fs.readFile(cssPath, "utf8");
  await fs.writeFile(cssPath, `${baseCss.trim()}\n\n@source "${slideSource}";\n`, "utf8");

  const payload = {
    schemaVersion: project.deck.schemaVersion,
    deck: project.deck,
    theme: project.theme,
    assetHashes: await assetHashes(assetsDir),
    slides: project.slides.map(({ sourcePath, number, ...slide }) => ({ number, ...slide })),
  };
  await fs.writeFile(
    path.join(resolvedOutput, "deck-runtime.json"),
    `${JSON.stringify(payload, null, 2)}\n`,
    "utf8",
  );
  return { outputDir: resolvedOutput, payload };
}
