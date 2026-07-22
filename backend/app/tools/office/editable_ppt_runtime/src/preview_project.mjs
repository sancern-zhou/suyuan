import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadProject } from "./source_loader.mjs";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const RUNTIME_DIR = path.resolve(MODULE_DIR, "..", "runtime");

function quoteTailwindSource(sourcePath) {
  return sourcePath.replaceAll("\\", "/").replaceAll('"', '\\"');
}

export async function materializePreview(projectDir, outputDir = path.join(projectDir, ".editable-ppt-runtime")) {
  const project = await loadProject(projectDir);
  const resolvedOutput = path.resolve(outputDir);
  await fs.mkdir(resolvedOutput, { recursive: true });
  await fs.cp(RUNTIME_DIR, resolvedOutput, { recursive: true, force: true });

  const slideSource = quoteTailwindSource(path.join(project.projectRoot, "slides"));
  const cssPath = path.join(resolvedOutput, "input.css");
  const baseCss = await fs.readFile(cssPath, "utf8");
  await fs.writeFile(cssPath, `${baseCss.trim()}\n\n@source "${slideSource}";\n`, "utf8");

  const payload = {
    schemaVersion: project.deck.schemaVersion,
    deck: project.deck,
    theme: project.theme,
    slides: project.slides.map(({ sourcePath, number, ...slide }) => ({ number, ...slide })),
  };
  await fs.writeFile(
    path.join(resolvedOutput, "deck-runtime.json"),
    `${JSON.stringify(payload, null, 2)}\n`,
    "utf8",
  );
  return { outputDir: resolvedOutput, payload };
}
