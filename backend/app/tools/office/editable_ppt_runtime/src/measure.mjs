import fs from "node:fs/promises";
import fsSync from "node:fs";
import crypto from "node:crypto";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import puppeteer from "puppeteer";
import { createServer } from "vite";

import { materializePreview } from "./preview_project.mjs";

export const VIEWPORT = Object.freeze({ width: 1440, height: 810 });
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const TAILWIND_CSS_PATH = path.resolve(MODULE_DIR, "..", "node_modules", "tailwindcss", "index.css");
const MEASUREMENT_RUNTIME_HASH = crypto
  .createHash("sha256")
  .update(fsSync.readFileSync(fileURLToPath(import.meta.url)))
  .digest("hex");

function newestPlaywrightChromium(homeDir) {
  const cacheRoot = path.join(homeDir, ".cache", "ms-playwright");
  if (!fsSync.existsSync(cacheRoot)) return null;
  const releases = fsSync
    .readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("chromium-"))
    .map((entry) => entry.name)
    .sort()
    .reverse();
  for (const release of releases) {
    for (const relativePath of ["chrome-linux64/chrome", "chrome-linux/chrome", "chrome-headless-shell-linux64/headless_shell"]) {
      const candidate = path.join(cacheRoot, release, relativePath);
      if (fsSync.existsSync(candidate)) return candidate;
    }
  }
  return null;
}

export function resolveBrowserExecutable({ env = process.env, homeDir = os.homedir() } = {}) {
  if (env.PUPPETEER_EXECUTABLE_PATH) {
    if (!fsSync.existsSync(env.PUPPETEER_EXECUTABLE_PATH)) {
      throw new Error(`PUPPETEER_EXECUTABLE_PATH does not exist: ${env.PUPPETEER_EXECUTABLE_PATH}`);
    }
    return env.PUPPETEER_EXECUTABLE_PATH;
  }
  try {
    const bundled = puppeteer.executablePath();
    if (bundled && fsSync.existsSync(bundled)) return bundled;
  } catch {
    // Fall through to the Playwright cache shared by the existing frontend runtime.
  }
  const playwright = newestPlaywrightChromium(homeDir);
  if (playwright) return playwright;
  throw new Error("BROWSER_EXECUTABLE_NOT_FOUND: configure PUPPETEER_EXECUTABLE_PATH or install Chromium");
}

export function analyzeBounds(element, viewport = VIEWPORT) {
  const { box } = element;
  const epsilon = 0.5;
  const outside =
    box.x < -epsilon ||
    box.y < -epsilon ||
    box.x + box.width > viewport.width + epsilon ||
    box.y + box.height > viewport.height + epsilon;
  if (!outside) return [];
  return [
    {
      code: "ELEMENT_OUT_OF_BOUNDS",
      elementId: element.id,
      message: `element exceeds ${viewport.width}x${viewport.height} slide bounds`,
      box,
    },
  ];
}

async function startPreviewServer(previewDir) {
  const server = await createServer({
    root: previewDir,
    configFile: false,
    logLevel: "silent",
    plugins: [tailwindcss()],
    resolve: {
      alias: [{ find: /^tailwindcss$/, replacement: TAILWIND_CSS_PATH }],
    },
    server: {
      host: "127.0.0.1",
      port: 0,
      strictPort: false,
    },
  });
  await server.listen();
  const address = server.httpServer?.address();
  if (!address || typeof address === "string") throw new Error("unable to resolve preview server port");
  return { server, baseUrl: `http://127.0.0.1:${address.port}` };
}

async function extractPage(page) {
  return page.evaluate(() => {
    const app = document.querySelector("#app");
    if (!app) throw new Error("preview app root is missing");
    const rootRect = app.getBoundingClientRect();
    const elements = [...app.querySelectorAll("[data-pptx-id], [data-pptx-ref]")].map((node) => {
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      const tagName = node.tagName.toLowerCase();
      const elementChildren = [...node.children];
      const supportsRichText = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"].includes(tagName) &&
        elementChildren.length > 0 &&
        elementChildren.every((child) => child.tagName === "SPAN" && child.children.length === 0);
      let textRuns = null;
      if (supportsRichText) {
        textRuns = [...node.childNodes].map((child) => {
          const rawText = child.textContent || "";
          const text = rawText.replace(/\s+/g, " ");
          if (!text.trim()) return null;
          const runNode = child.nodeType === Node.ELEMENT_NODE ? child : node;
          const runStyle = window.getComputedStyle(runNode);
          return {
            text,
            elementId: child.nodeType === Node.ELEMENT_NODE
              ? child.getAttribute("data-pptx-id")
              : null,
            style: {
              color: runStyle.color,
              fontFamily: runStyle.fontFamily,
              fontSize: runStyle.fontSize,
              fontWeight: runStyle.fontWeight,
              fontStyle: runStyle.fontStyle,
            },
          };
        }).filter(Boolean);
        if (textRuns.length) {
          textRuns[0].text = textRuns[0].text.replace(/^\s+/, "");
          textRuns[textRuns.length - 1].text = textRuns[textRuns.length - 1].text.replace(/\s+$/, "");
        }
      }
      return {
        id: node.getAttribute("data-pptx-id") || node.getAttribute("data-pptx-ref"),
        source: node.hasAttribute("data-pptx-ref") ? "native-ref" : "dom",
        tagName,
        text: node.innerText || "",
        textRuns,
        src: node.tagName === "IMG" ? node.getAttribute("src") : null,
        hasTaggedDescendant: Boolean(node.querySelector("[data-pptx-id], [data-pptx-ref]")),
        hasUntaggedDirectText: Boolean(node.querySelector("[data-pptx-id], [data-pptx-ref]")) &&
          [...node.childNodes].some((child) =>
            child.nodeType === Node.TEXT_NODE && (child.textContent || "").trim()),
        hasUntaggedTextDescendant: [...node.querySelectorAll("*")].some((child) =>
          (child.innerText || "").trim() &&
          !child.closest("[data-pptx-ref]") &&
          !child.matches("[data-pptx-id], [data-pptx-ref]") &&
          !child.querySelector("[data-pptx-id], [data-pptx-ref]")),
        box: {
          x: rect.left - rootRect.left,
          y: rect.top - rootRect.top,
          width: rect.width,
          height: rect.height,
        },
        style: {
          color: style.color,
          backgroundColor: style.backgroundColor,
          borderColor: style.borderColor,
          borderWidth: style.borderWidth,
          borderRadius: style.borderRadius,
          boxShadow: style.boxShadow,
          backgroundImage: style.backgroundImage,
          filter: style.filter,
          transform: style.transform,
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
          fontStyle: style.fontStyle,
          lineHeight: style.lineHeight,
          textAlign: style.textAlign,
          opacity: style.opacity,
          overflow: style.overflow,
          zIndex: style.zIndex,
        },
      };
    });
    const ids = elements.map((element) => element.id);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const missingImages = [...app.querySelectorAll("img")]
      .filter((image) => !image.complete || image.naturalWidth === 0)
      .map((image) => image.getAttribute("src") || "");
    const viteOverlay = document.querySelector("vite-error-overlay");
    const viteError = viteOverlay
      ? (viteOverlay.shadowRoot?.textContent || viteOverlay.textContent || "Vite error overlay detected").trim()
      : null;
    return {
      slideId: app.dataset.slideId,
      elements,
      diagnostics: {
        duplicateIds,
        missingImages,
        scrollWidth: app.scrollWidth,
        scrollHeight: app.scrollHeight,
        cssReady: window.getComputedStyle(document.documentElement)
          .getPropertyValue("--ppt-runtime-css-ready").trim() === "1",
        viteError,
        runtimeError: window.__PPT_ERROR__ || null,
      },
    };
  });
}

export function runtimeDiagnosticIssues(diagnostics) {
  const issues = [];
  if (!diagnostics.cssReady) {
    issues.push({
      code: "RUNTIME_CSS_NOT_READY",
      elementId: null,
      message: "editable PPT runtime stylesheet did not finish loading",
    });
  }
  if (diagnostics.viteError) {
    issues.push({
      code: "RUNTIME_BUILD_FAILED",
      elementId: null,
      message: String(diagnostics.viteError).slice(0, 2000),
    });
  }
  if (diagnostics.browserErrors?.length) {
    issues.push({
      code: "BROWSER_RUNTIME_ERROR",
      elementId: null,
      message: diagnostics.browserErrors.join("\n").slice(0, 2000),
    });
  }
  return issues;
}

export function assetReferenceIssues(elements) {
  return elements
    .filter((element) => element.tagName === "img" && element.src)
    .filter((element) => !/^(?:\.\/|\/)?assets\//.test(element.src) && !element.src.startsWith("data:image/"))
    .map((element) => ({
      code: "ASSET_REFERENCE_OUTSIDE_PROJECT",
      elementId: element.id,
      message: `image source must be stored under project assets/: ${element.src}`,
    }));
}

function diagnosticIssues(result) {
  const issues = [
    ...runtimeDiagnosticIssues(result.diagnostics),
    ...assetReferenceIssues(result.elements),
    ...result.elements.flatMap((element) => analyzeBounds(element)),
  ];
  for (const id of result.diagnostics.duplicateIds) {
    issues.push({ code: "DUPLICATE_ELEMENT_ID", elementId: id, message: `duplicate element id: ${id}` });
  }
  for (const src of result.diagnostics.missingImages) {
    issues.push({ code: "IMAGE_LOAD_FAILED", elementId: null, message: `image failed to load: ${src}` });
  }
  if (result.diagnostics.scrollWidth > VIEWPORT.width || result.diagnostics.scrollHeight > VIEWPORT.height) {
    issues.push({
      code: "SLIDE_CONTENT_OVERFLOW",
      elementId: null,
      message: "slide content exceeds fixed viewport",
      scrollWidth: result.diagnostics.scrollWidth,
      scrollHeight: result.diagnostics.scrollHeight,
    });
  }
  return issues;
}

export async function measureDeck(projectDir, outputDir, options = {}) {
  const previewDir = path.join(outputDir, "runtime");
  const screenshotsDir = path.join(outputDir, "previews");
  await fs.mkdir(screenshotsDir, { recursive: true });
  const { payload } = await materializePreview(projectDir, previewDir);
  const pages = options.pages || payload.slides.map((slide) => slide.number);
  for (const pageNumber of pages) {
    if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > payload.slides.length) {
      throw new Error(`page must be between 1 and ${payload.slides.length}`);
    }
  }
  const dirtySlides = new Set(options.dirtySlides || []);
  const cacheDir = options.cacheDir ? path.resolve(options.cacheDir) : null;
  if (cacheDir) await fs.mkdir(cacheDir, { recursive: true });
  const resultByPage = new Map();
  const misses = [];
  for (const pageNumber of pages) {
    const slide = payload.slides[pageNumber - 1];
    const referencedAssets = Object.fromEntries(Object.entries(payload.assetHashes || {}).filter(([name]) => slide.html.includes(`assets/${name}`)));
    const digest = crypto.createHash("sha256").update(JSON.stringify({
      slide,
      theme: payload.theme,
      referencedAssets,
      runtimeHash: payload.runtimeHash,
      measurementRuntimeHash: MEASUREMENT_RUNTIME_HASH,
      viewport: VIEWPORT,
    })).digest("hex");
    const jsonPath = cacheDir ? path.join(cacheDir, `${slide.id}-${digest}.json`) : null;
    const pngPath = cacheDir ? path.join(cacheDir, `${slide.id}-${digest}.png`) : null;
    const screenshotPath = path.join(screenshotsDir, `page-${String(pageNumber).padStart(3, "0")}.png`);
    if (cacheDir && !dirtySlides.has(slide.id) && fsSync.existsSync(jsonPath) && fsSync.existsSync(pngPath)) {
      const cached = JSON.parse(await fs.readFile(jsonPath, "utf8"));
      await fs.copyFile(pngPath, screenshotPath);
      resultByPage.set(pageNumber, { ...cached, screenshotPath, cacheHit: true, cacheKey: digest });
    } else {
      misses.push({ pageNumber, slide, digest, jsonPath, pngPath, screenshotPath });
    }
  }
  let server;
  let baseUrl;
  let browser;
  try {
    let page;
    let browserErrors = [];
    if (misses.length) {
      ({ server, baseUrl } = await startPreviewServer(previewDir));
      browser = await puppeteer.launch({
        executablePath: resolveBrowserExecutable(),
        headless: true,
        args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
      });
      page = await browser.newPage();
      await page.setViewport({ ...VIEWPORT, deviceScaleFactor: 1 });
      page.on("pageerror", (error) => browserErrors.push(String(error?.stack || error)));
      page.on("console", (message) => {
        const text = message.text();
        if (message.type() === "error" && !/^Failed to load resource:/i.test(text)) {
          browserErrors.push(text);
        }
      });
      page.on("requestfailed", (request) => {
        if (["script", "stylesheet"].includes(request.resourceType())) {
          browserErrors.push(`${request.resourceType()} request failed: ${request.url()} (${request.failure()?.errorText || "unknown"})`);
        }
      });
    }
    for (const miss of misses) {
      const { pageNumber, digest, jsonPath, pngPath, screenshotPath } = miss;
      browserErrors = [];
      await page.goto(`${baseUrl}/?page=${pageNumber}`, { waitUntil: "networkidle0", timeout: 30_000 });
      await page.waitForFunction(
        () => window.__PPT_READY__ === true || Boolean(window.__PPT_ERROR__),
        { timeout: 30_000 },
      );
      const measured = await extractPage(page);
      measured.diagnostics.browserErrors = [...new Set(browserErrors)];
      if (measured.diagnostics.runtimeError) throw new Error(measured.diagnostics.runtimeError);
      await page.screenshot({ path: screenshotPath, clip: { x: 0, y: 0, ...VIEWPORT } });
      const issues = diagnosticIssues(measured);
      const result = {
        pageNumber,
        slideId: measured.slideId,
        elements: measured.elements,
        diagnostics: measured.diagnostics,
        issues,
        screenshotPath,
        cacheHit: false,
        cacheKey: digest,
      };
      if (cacheDir && issues.length === 0) {
        const cached = { ...result };
        delete cached.screenshotPath;
        await fs.writeFile(jsonPath, `${JSON.stringify(cached)}\n`, "utf8");
        await fs.copyFile(screenshotPath, pngPath);
      }
      resultByPage.set(pageNumber, result);
    }
    const results = pages.map((pageNumber) => resultByPage.get(pageNumber));
    const hits = results.filter((item) => item.cacheHit).length;
    return { viewport: { ...VIEWPORT }, previewDir, pages: results, cache: { enabled: Boolean(cacheDir), hits, misses: results.length - hits } };
  } finally {
    if (browser) await browser.close();
    if (server) await server.close();
  }
}
