import { bindKeyboardNavigation, pageFromSearch } from "./controller.mjs";

function cssTokenName(name) {
  return `--${name.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`)}`;
}

function applyTheme(theme) {
  for (const [name, value] of Object.entries(theme || {})) {
    if (name === "schemaVersion" || name === "id" || value === null || typeof value === "object") continue;
    const normalized = typeof value === "string" && /^[0-9A-Fa-f]{6}$/.test(value) ? `#${value}` : String(value);
    document.documentElement.style.setProperty(cssTokenName(name), normalized);
  }
}

function renderTable(target, element) {
  const table = document.createElement("table");
  table.dataset.previewKind = "table";
  for (const row of element.data?.rows || []) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = typeof cell === "object" ? String(cell.text ?? "") : String(cell);
      tr.append(td);
    }
    table.append(tr);
  }
  target.replaceChildren(table);
}

function renderChart(target, element) {
  const chart = document.createElement("div");
  chart.dataset.previewKind = "chart";
  chart.style.cssText = "display:flex;align-items:end;gap:12px;width:100%;height:100%;padding:24px;overflow:hidden;box-sizing:border-box";
  const values = element.data?.series?.flatMap((series) => series.values || []) || [];
  const max = Math.max(1, ...values.map(Number));
  for (const value of values) {
    const bar = document.createElement("div");
    bar.style.cssText = `flex:1;min-width:0;height:${(Number(value) / max) * 100}%;background:var(--primary,#174a7c)`;
    bar.title = String(value);
    chart.append(bar);
  }
  target.replaceChildren(chart);
}

function renderDiagram(target, element) {
  const diagram = document.createElement("div");
  diagram.dataset.previewKind = "diagram";
  diagram.style.cssText = "display:flex;align-items:center;justify-content:space-around;width:100%;height:100%;gap:16px";
  for (const node of element.data?.nodes || []) {
    const box = document.createElement("div");
    box.textContent = String(node.label || node.id);
    box.style.cssText = "padding:12px 20px;border:2px solid var(--primary,#174a7c);border-radius:8px";
    diagram.append(box);
  }
  target.replaceChildren(diagram);
}

function renderNativeElements(slide) {
  for (const element of slide.nativeElements || []) {
    const target = document.querySelector(`[data-pptx-ref="${CSS.escape(element.id)}"]`);
    if (!target) continue;
    if (element.kind === "chart") renderChart(target, element);
    if (element.kind === "table") renderTable(target, element);
    if (element.kind === "diagram") renderDiagram(target, element);
  }
}

async function waitForImages() {
  await Promise.all(
    [...document.images].map((image) => {
      if (image.complete) return Promise.resolve();
      return new Promise((resolve) => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", resolve, { once: true });
      });
    }),
  );
}

async function boot() {
  window.__PPT_READY__ = false;
  const app = document.querySelector("#app");
  try {
    const response = await fetch("/deck-runtime.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`unable to load deck runtime: ${response.status}`);
    const deck = await response.json();
    let currentPage = pageFromSearch(window.location.search, deck.slides.length);
    applyTheme(deck.theme);

    const render = (page) => {
      currentPage = page;
      const slide = deck.slides[page - 1];
      app.innerHTML = slide.html;
      app.dataset.page = String(page);
      app.dataset.slideId = slide.id;
      renderNativeElements(slide);
      window.history.replaceState(null, "", `?page=${page}`);
    };
    render(currentPage);
    bindKeyboardNavigation({ getPage: () => currentPage, setPage: render, pageCount: deck.slides.length });
    await Promise.all([document.fonts?.ready || Promise.resolve(), waitForImages()]);
    window.__PPT_READY__ = true;
  } catch (error) {
    app.innerHTML = `<div class="editable-ppt-error">${String(error.message || error)}</div>`;
    window.__PPT_ERROR__ = String(error.stack || error);
  }
}

boot();
