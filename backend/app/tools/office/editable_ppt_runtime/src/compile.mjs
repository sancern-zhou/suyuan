import { createRequire } from "node:module";
import fs from "node:fs/promises";
import path from "node:path";

import JSZip from "jszip";

import { SCHEMA_VERSION } from "./contracts.mjs";
import { measureDeck } from "./measure.mjs";
import { addBasicElement, normalizeColor } from "./pptx/basic_adapter.mjs";
import { addNativeElement } from "./pptx/semantic_adapter.mjs";
import { auditFallbacks } from "./pptx/strict_policy.mjs";
import { loadProject } from "./source_loader.mjs";

const require = createRequire(import.meta.url);
const PptxGenJS = require("pptxgenjs");

function emptyNativeCounts() {
  return { chart: 0, table: 0, diagram: 0 };
}

async function auditPptx(pptxPath) {
  const zip = await JSZip.loadAsync(await fs.readFile(pptxPath));
  const names = Object.keys(zip.files);
  return {
    slides: names.filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name)).length,
    charts: names.filter((name) => /^ppt\/charts\/chart\d+\.xml$/.test(name)).length,
    embeddedWorkbooks: names.filter((name) => /^ppt\/embeddings\/.+\.xlsx$/.test(name)).length,
    hasPresentation: names.includes("ppt/presentation.xml"),
    hasContentTypes: names.includes("[Content_Types].xml"),
  };
}

function findMeasuredBox(page, id) {
  const measured = page.elements.find((element) => element.id === id && element.source === "native-ref");
  if (!measured) throw new Error(`NATIVE_PLACEHOLDER_NOT_MEASURED: ${id}`);
  return measured.box;
}

export function unsupportedStyleIssues(measurement) {
  const rules = [
    ["backgroundImage", (value) => value && value !== "none"],
    ["filter", (value) => value && value !== "none"],
    ["transform", (value) => value && value !== "none"],
    ["boxShadow", (value) => value && value !== "none"],
  ];
  return measurement.pages.flatMap((page) => page.elements.flatMap((element) => rules
    .filter(([name, unsupported]) => unsupported(element.style?.[name]))
    .map(([name]) => ({ code: "UNSUPPORTED_STYLE_STRICT", slideId: page.slideId, elementId: element.id, message: `${name} cannot be preserved as a native object` }))));
}

function resolveImageSource(element, projectRoot) {
  if (element.tagName !== "img" || !element.src || element.src.startsWith("data:")) return element;
  if (/^[a-z]+:\/\//i.test(element.src)) throw new Error(`REMOTE_IMAGE_NOT_SUPPORTED: ${element.src}`);
  const resolved = path.resolve(projectRoot, element.src.replace(/^\/+/, ""));
  const relative = path.relative(projectRoot, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`IMAGE_PATH_OUTSIDE_PROJECT: ${element.src}`);
  return { ...element, src: resolved };
}

function addSlideContent(pptx, pptxSlide, slideSpec, measuredPage, theme, report, projectRoot) {
  pptxSlide.background = { color: normalizeColor(theme.canvas) || "FFFFFF" };
  const nativeIds = new Set((slideSpec.nativeElements || []).map((element) => element.id));
  for (const element of measuredPage.elements) {
    if (element.id === "slide-root" || element.source === "native-ref" || nativeIds.has(element.id)) continue;
    const added = addBasicElement(pptxSlide, resolveImageSource(element, projectRoot), pptx);
    if (added?.kind === "text") report.native.text += 1;
    if (added?.kind === "shape") report.native.shape += 1;
    if (added?.kind === "image") report.native.image += 1;
  }
  for (const element of slideSpec.nativeElements || []) {
    addNativeElement(pptxSlide, element, findMeasuredBox(measuredPage, element.id), theme, pptx);
    report.native[element.kind] += 1;
  }
  if (slideSpec.speakerNotes?.length) {
    pptxSlide.addNotes(slideSpec.speakerNotes.map((text) => ({ text: String(text) })));
  }
}

export async function inspectProject(projectDir) {
  const project = await loadProject(projectDir);
  return {
    success: true,
    schemaVersion: project.deck.schemaVersion,
    projectDir: project.projectRoot,
    deckId: project.deck.id,
    slideCount: project.slides.length,
    slideIds: project.slides.map((slide) => slide.id),
    editable: project.deck.editable || "strict",
  };
}

export async function renderPreview(projectDir, outputDir, options = {}) {
  const measurement = await measureDeck(projectDir, outputDir, options);
  return { success: true, ...measurement };
}

export async function compileDeck(projectDir, outputDir, options = {}) {
  const startedAt = Date.now();
  const fileName = options.fileName || "presentation.pptx";
  if (path.basename(fileName) !== fileName || path.extname(fileName).toLowerCase() !== ".pptx") {
    throw new Error(`OUTPUT_FILE_NAME_INVALID: ${fileName}`);
  }
  const project = await loadProject(projectDir);
  const editable = options.editable || project.deck.editable || "strict";
  await fs.mkdir(outputDir, { recursive: true });
  const measurement = await measureDeck(projectDir, path.join(outputDir, "measurement"), {
    pages: options.pages,
    dirtySlides: options.dirtySlides,
    cacheDir: options.cacheDir,
  });
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Suyuan Editable PPT Agent";
  pptx.subject = project.deck.title || project.deck.id;
  pptx.title = project.deck.title || project.deck.id;
  pptx.company = "Suyuan";
  pptx.lang = "zh-CN";
  pptx.theme = {
    headFontFace: project.theme.fontTitle || "Microsoft YaHei",
    bodyFontFace: project.theme.fontBody || "Microsoft YaHei",
    lang: "zh-CN",
  };

  const fallbackAudit = auditFallbacks(options.fallbacks || [], editable);
  const styleIssues = unsupportedStyleIssues(measurement);
  const report = {
    schemaVersion: SCHEMA_VERSION,
    deckId: project.deck.id,
    slideCount: project.slides.length,
    editable,
    native: { text: 0, shape: 0, image: 0, ...emptyNativeCounts() },
    allowedRasterFallbacks: fallbackAudit.allowedRasterFallbacks,
    forbiddenRasterFallbacks: fallbackAudit.forbiddenRasterFallbacks,
    forbiddenElementIds: fallbackAudit.forbiddenElementIds,
    issues: [...styleIssues, ...measurement.pages.flatMap((page) =>
      page.issues.map((issue) => ({ ...issue, pageNumber: page.pageNumber, slideId: page.slideId })),
    )],
    measurement: {
      viewport: measurement.viewport,
      previewDir: measurement.previewDir,
      screenshots: measurement.pages.map((page) => page.screenshotPath),
      cache: measurement.cache,
    },
  };
  if (editable === "strict" && report.forbiddenRasterFallbacks > 0) {
    return { success: false, report, error: "RASTER_FALLBACK_FORBIDDEN" };
  }
  if (editable === "strict" && styleIssues.length > 0) {
    return { success: false, report, error: "UNSUPPORTED_STYLE_STRICT" };
  }

  const measuredBySlide = new Map(measurement.pages.map((page) => [page.slideId, page]));
  for (const slideSpec of project.slides) {
    const measuredPage = measuredBySlide.get(slideSpec.id);
    if (!measuredPage) throw new Error(`MEASUREMENT_MISSING: ${slideSpec.id}`);
    const pptxSlide = pptx.addSlide();
    addSlideContent(pptx, pptxSlide, slideSpec, measuredPage, project.theme, report, project.projectRoot);
  }

  const pptxPath = path.join(outputDir, fileName);
  await pptx.writeFile({ fileName: pptxPath });
  report.ooxml = await auditPptx(pptxPath);
  if (!report.ooxml.hasPresentation || !report.ooxml.hasContentTypes || report.ooxml.slides !== report.slideCount) {
    report.issues.push({ code: "OOXML_STRUCTURE_INVALID", message: "generated PPTX structure is incomplete" });
  }
  report.durationMs = Date.now() - startedAt;
  report.outputSizeBytes = (await fs.stat(pptxPath)).size;
  report.rssBytes = process.memoryUsage().rss;
  const reportPath = path.join(outputDir, "compile-report.json");
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return {
    success: report.forbiddenRasterFallbacks === 0 && !report.issues.some((issue) => issue.code === "OOXML_STRUCTURE_INVALID"),
    pptxPath,
    reportPath,
    report,
  };
}
