import fs from "node:fs/promises";
import fsSync from "node:fs";
import crypto from "node:crypto";
import os from "node:os";
import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import puppeteer from "puppeteer";
import { createServer } from "vite";

import { materializePreview } from "./preview_project.mjs";

export const VIEWPORT = Object.freeze({ width: 1440, height: 810 });

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
      return {
        id: node.getAttribute("data-pptx-id") || node.getAttribute("data-pptx-ref"),
        source: node.hasAttribute("data-pptx-ref") ? "native-ref" : "dom",
        tagName: node.tagName.toLowerCase(),
        text: node.innerText || "",
        src: node.tagName === "IMG" ? node.getAttribute("src") : null,
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
    return {
      slideId: app.dataset.slideId,
      elements,
      diagnostics: {
        duplicateIds,
        missingImages,
        scrollWidth: app.scrollWidth,
        scrollHeight: app.scrollHeight,
        runtimeError: window.__PPT_ERROR__ || null,
      },
    };
  });
}

function diagnosticIssues(result) {
  const issues = result.elements.flatMap((element) => analyzeBounds(element));
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
    const digest = crypto.createHash("sha256").update(JSON.stringify({ slide, theme: payload.theme, viewport: VIEWPORT })).digest("hex");
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
    if (misses.length) {
      ({ server, baseUrl } = await startPreviewServer(previewDir));
      browser = await puppeteer.launch({
        executablePath: resolveBrowserExecutable(),
        headless: true,
        args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
      });
      page = await browser.newPage();
      await page.setViewport({ ...VIEWPORT, deviceScaleFactor: 1 });
    }
    for (const miss of misses) {
      const { pageNumber, digest, jsonPath, pngPath, screenshotPath } = miss;
      await page.goto(`${baseUrl}/?page=${pageNumber}`, { waitUntil: "networkidle0", timeout: 30_000 });
      await page.waitForFunction(
        () => window.__PPT_READY__ === true || Boolean(window.__PPT_ERROR__),
        { timeout: 30_000 },
      );
      const measured = await extractPage(page);
      if (measured.diagnostics.runtimeError) throw new Error(measured.diagnostics.runtimeError);
      await page.screenshot({ path: screenshotPath, clip: { x: 0, y: 0, ...VIEWPORT } });
      const result = {
        pageNumber,
        slideId: measured.slideId,
        elements: measured.elements,
        diagnostics: measured.diagnostics,
        issues: diagnosticIssues(measured),
        screenshotPath,
        cacheHit: false,
        cacheKey: digest,
      };
      if (cacheDir) {
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
