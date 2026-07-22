import fs from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";

import { validateDeck, validateSlide } from "./contracts.mjs";

export function resolveInside(projectRoot, relativePath) {
  const root = path.resolve(projectRoot);
  const candidate = path.resolve(root, relativePath);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) {
    throw new Error(`path is outside project root: ${relativePath}`);
  }
  return candidate;
}

export function loadSlideSource(source, filename = "slide.js") {
  const context = vm.createContext(
    {},
    {
      codeGeneration: { strings: false, wasm: false },
      name: `editable-ppt:${filename}`,
    },
  );
  new vm.Script("globalThis.window = Object.freeze({ slideDataMap: new Map() });")
    .runInContext(context, { timeout: 200 });
  const script = new vm.Script(source, { filename });
  script.runInContext(context, { timeout: 200 });
  const serialized = new vm.Script("JSON.stringify(Array.from(window.slideDataMap.entries()))")
    .runInContext(context, { timeout: 200 });
  const entries = JSON.parse(serialized);
  if (entries.length !== 1) {
    throw new Error(`${filename} must register exactly one slide`);
  }
  const [[number, slide]] = entries;
  if (!Number.isInteger(number) || number < 1) {
    throw new Error(`${filename} must use a positive integer page number`);
  }
  const validation = validateSlide(slide);
  if (!validation.ok) {
    throw new Error(`${filename} is invalid: ${validation.errors.join("; ")}`);
  }
  return { number, ...slide };
}

async function readJson(filePath, label) {
  let raw;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch (error) {
    throw new Error(`unable to read ${label} at ${filePath}: ${error.message}`);
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`invalid JSON in ${label} at ${filePath}: ${error.message}`);
  }
}

async function loadSlides(projectRoot) {
  const slidesDir = resolveInside(projectRoot, "slides");
  const entries = await fs.readdir(slidesDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && /^slide-\d+\.js$/.test(entry.name))
    .map((entry) => entry.name)
    .sort();
  if (files.length === 0) throw new Error("project must contain at least one slides/slide-NNN.js file");
  const slides = [];
  for (const file of files) {
    const filePath = resolveInside(projectRoot, path.join("slides", file));
    const source = await fs.readFile(filePath, "utf8");
    slides.push({ ...loadSlideSource(source, file), sourcePath: filePath });
  }
  slides.sort((left, right) => left.number - right.number);
  const numbers = slides.map((slide) => slide.number);
  if (new Set(numbers).size !== numbers.length) throw new Error("slide page numbers must be unique");
  const ids = slides.map((slide) => slide.id);
  if (new Set(ids).size !== ids.length) throw new Error("slide ids must be unique");
  return slides;
}

export async function loadProject(projectDir) {
  const projectRoot = path.resolve(projectDir);
  const deck = await readJson(resolveInside(projectRoot, "deck.json"), "deck.json");
  const deckValidation = validateDeck(deck);
  if (!deckValidation.ok) throw new Error(`deck.json is invalid: ${deckValidation.errors.join("; ")}`);
  const theme = await readJson(resolveInside(projectRoot, deck.theme), "theme");
  const slides = await loadSlides(projectRoot);
  const loadedIds = slides.map((slide) => slide.id);
  if (JSON.stringify(loadedIds) !== JSON.stringify(deck.slides)) {
    throw new Error(`deck slide order does not match source slides: expected ${deck.slides.join(",")}; loaded ${loadedIds.join(",")}`);
  }
  return { projectRoot, deck, theme, slides };
}
