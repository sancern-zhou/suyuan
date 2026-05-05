const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const {
  autoFontSize,
  imageSizingContain,
  imageSizingCrop,
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers");

const argv = process.argv.slice(2);
if (argv.length < 2) {
  console.error("Usage: node pptxgen_renderer.js <spec.json> <output.pptx>");
  process.exit(2);
}

const specPath = path.resolve(argv[0]);
const outputPath = path.resolve(argv[1]);
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const theme = spec.theme || {};

function color(value, fallback) {
  const raw = String(value || "").trim().replace(/^#/, "");
  const match = raw.match(/^([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?$/);
  return match ? match[1].toUpperCase() : fallback;
}

function text(value) {
  return value === undefined || value === null ? "" : String(value);
}

function fontSize(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 6 && parsed <= 60 ? parsed : fallback;
}

function fitTextOptions(value, fontFace, opts = {}) {
  return autoFontSize(value, fontFace, {
    ...opts,
    minFontSize: opts.minFontSize ?? 8,
    maxFontSize: opts.maxFontSize ?? opts.fontSize ?? 18,
  });
}

const fonts = {
  head: text(theme.headFontFace || "Microsoft YaHei") || "Microsoft YaHei",
  body: text(theme.bodyFontFace || "Microsoft YaHei") || "Microsoft YaHei",
};

const palette = {
  primary: color(theme.primary, "2563EB"),
  secondary: color(theme.secondary, "0F766E"),
  accent: color(theme.accent, "DC2626"),
  text: color(theme.text || theme.foreground, "1F2937"),
  muted: color(theme.muted, "6B7280"),
  bg: color(theme.bg || theme.background, "FFFFFF"),
  surface: color(theme.surface, "F8FAFC"),
  line: color(theme.line, "D1D5DB"),
};

const pptx = new pptxgen();
pptx.layout = spec.layout || "LAYOUT_WIDE";
pptx.author = spec.author || "suyuan-agent";
pptx.subject = spec.subject || "";
pptx.title = spec.title || "Presentation";
pptx.company = spec.company || "";
pptx.lang = spec.lang || "zh-CN";
pptx.theme = {
  headFontFace: fonts.head,
  bodyFontFace: fonts.body,
  lang: spec.lang || "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });

function addTitle(slide, title, subtitle) {
  if (title) {
    slide.addText(title, {
      x: 0.6, y: 0.38, w: 12.1, h: 0.52,
      ...fitTextOptions(title, fonts.head, { x: 0.6, y: 0.38, w: 12.1, h: 0.52, fontSize: 23, minFontSize: 13 }),
      bold: true, color: palette.text,
      margin: 0.02, breakLine: false, fit: "shrink",
    });
  }
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.62, y: 0.96, w: 11.8, h: 0.32,
      ...fitTextOptions(subtitle, fonts.body, { x: 0.62, y: 0.96, w: 11.8, h: 0.32, fontSize: 9.5, minFontSize: 7 }),
      color: palette.muted, margin: 0.01, fit: "shrink",
    });
  }
}

function addBullets(slide, items, x, y, w, h, opts = {}) {
  const rich = (items || []).map((item) => ({
    text: text(typeof item === "string" ? item : item.text || ""),
    options: { bullet: { type: "bullet" }, breakLine: true },
  }));
  slide.addText(rich.length ? rich : " ", {
    x, y, w, h,
    ...fitTextOptions(rich.length ? rich : " ", fonts.body, { x, y, w, h, fontSize: fontSize(opts.fontSize, 15), minFontSize: opts.minFontSize ?? 8 }),
    color: color(opts.color, palette.text),
    margin: 0.08,
    breakLine: false,
    fit: "shrink",
    valign: "top",
  });
}

function addBodyText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text || " ", {
    x, y, w, h,
    ...fitTextOptions(text || " ", opts.fontFace || fonts.body, { x, y, w, h, fontSize: fontSize(opts.fontSize, 14), minFontSize: opts.minFontSize ?? 8 }),
    color: color(opts.color, palette.text),
    margin: 0.07,
    fit: "shrink",
    valign: "top",
    breakLine: false,
  });
}

function addTable(slide, table, x, y, w, h) {
  const rows = Array.isArray(table) ? table : table?.rows || [];
  slide.addTable(rows, {
    x, y, w, h,
    fontFace: fonts.body,
    fontSize: 9.5,
    color: palette.text,
    border: { type: "solid", color: palette.line, pt: 0.5 },
    fill: palette.bg,
    margin: 0.04,
    autoFit: true,
  });
}

function addImage(slide, image, x, y, w, h) {
  if (!image) return;
  const imagePath = image.path ? path.resolve(image.path) : null;
  const sizing = image.fit === "crop" ? imageSizingCrop : imageSizingContain;
  if (imagePath && fs.existsSync(imagePath)) {
    const box = sizing(imagePath, x, y, w, h);
    slide.addImage({ path: imagePath, x: box.x, y: box.y, w: box.w, h: box.h });
  } else if (image.data) {
    slide.addImage({ data: image.data, x, y, w, h });
  }
}

function addChart(slide, chart, x, y, w, h) {
  if (!chart || !chart.data) return;
  const typeName = String(chart.type || "bar").toLowerCase();
  const typeMap = {
    bar: pptx.ChartType.bar,
    line: pptx.ChartType.line,
    pie: pptx.ChartType.pie,
    doughnut: pptx.ChartType.doughnut,
    scatter: pptx.ChartType.scatter,
  };
  slide.addChart(typeMap[typeName] || pptx.ChartType.bar, chart.data, {
    x, y, w, h,
    showLegend: chart.showLegend ?? true,
    showValue: chart.showValue ?? false,
    catAxisLabelFontFace: fonts.body,
    valAxisLabelFontFace: fonts.body,
    title: chart.title || "",
    titleFontFace: fonts.head,
  });
}

function addItems(slide, items, x, y, w, h, opts = {}) {
  const list = Array.isArray(items) ? items : [];
  const rowH = h / Math.max(1, list.length);
  list.forEach((item, index) => {
    const title = text(typeof item === "string" ? item : item.title || item.label || item.text || "");
    const body = text(typeof item === "string" ? "" : item.body || item.description || item.value || "");
    const y0 = y + index * rowH;
    slide.addShape(pptx.ShapeType.ellipse, {
      x, y: y0 + 0.08, w: 0.32, h: 0.32,
      fill: { color: opts.badgeColor || palette.primary },
      line: { transparency: 100 },
    });
    slide.addText(String(index + 1), {
      x, y: y0 + 0.13, w: 0.32, h: 0.16,
      fontFace: fonts.body, fontSize: 7.5, bold: true,
      color: palette.bg, align: "center", margin: 0,
    });
    slide.addText(title, {
      ...fitTextOptions(title, fonts.head, { x: x + 0.48, y: y0 + 0.02, w: w - 0.48, h: Math.min(0.32, rowH * 0.45), fontSize: opts.titleSize || 13, minFontSize: 8 }),
      bold: true, color: opts.titleColor || palette.text, margin: 0.02,
    });
    if (body) {
      slide.addText(body, {
        ...fitTextOptions(body, fonts.body, { x: x + 0.48, y: y0 + 0.36, w: w - 0.48, h: Math.max(0.25, rowH - 0.42), fontSize: opts.bodySize || 10.5, minFontSize: 7 }),
        color: opts.bodyColor || palette.muted, margin: 0.02, valign: "top",
      });
    }
  });
}

function addFooter(slide, idx) {
  if (spec.footer === false) return;
  slide.addShape(pptx.ShapeType.line, {
    x: 0.6, y: 7.05, w: 12.1, h: 0,
    line: { color: palette.line, width: 0.5 },
  });
  slide.addText(String(idx), {
    x: 12.1, y: 7.12, w: 0.6, h: 0.18,
    fontSize: 7.5, color: palette.muted, align: "right",
    margin: 0,
  });
}

function renderSlide(slideSpec, idx) {
  const slide = pptx.addSlide();
  slide.background = { color: color(slideSpec.background, palette.bg) };
  const type = slideSpec.type || "bullets";

  if (type === "title") {
    slide.addText(slideSpec.title || spec.title || "", {
      x: 0.85, y: 2.2, w: 11.7, h: 0.85,
      ...fitTextOptions(slideSpec.title || spec.title || "", fonts.head, { x: 0.85, y: 2.2, w: 11.7, h: 0.85, fontSize: 32, minFontSize: 18 }),
      bold: true, color: palette.text,
      align: "center", margin: 0.02, fit: "shrink",
    });
    if (slideSpec.subtitle) {
      slide.addText(slideSpec.subtitle, {
        x: 1.5, y: 3.15, w: 10.4, h: 0.5,
        ...fitTextOptions(slideSpec.subtitle, fonts.body, { x: 1.5, y: 3.15, w: 10.4, h: 0.5, fontSize: 14, minFontSize: 9 }),
        color: palette.muted,
        align: "center", margin: 0.02, fit: "shrink",
      });
    }
  } else if (type === "section") {
    slide.addShape(pptx.ShapeType.rect, {
      x: 0.65, y: 2.2, w: 0.1, h: 1.1,
      fill: { color: palette.primary }, line: { transparency: 100 },
    });
    slide.addText(slideSpec.title || "", {
      x: 0.95, y: 2.25, w: 11.4, h: 0.78,
      ...fitTextOptions(slideSpec.title || "", fonts.head, { x: 0.95, y: 2.25, w: 11.4, h: 0.78, fontSize: 30, minFontSize: 16 }),
      bold: true, color: palette.text,
      margin: 0.02, fit: "shrink",
    });
    addBodyText(slide, slideSpec.subtitle || "", 0.97, 3.1, 10.8, 0.5, { fontSize: 13, color: palette.muted });
  } else {
    addTitle(slide, slideSpec.title, slideSpec.subtitle);

    if (type === "two_column") {
      addBodyText(slide, slideSpec.leftTitle || "", 0.75, 1.55, 5.7, 0.3, { fontSize: 13, color: palette.primary });
      addBodyText(slide, slideSpec.rightTitle || "", 6.9, 1.55, 5.7, 0.3, { fontSize: 13, color: palette.primary });
      if (Array.isArray(slideSpec.left)) addBullets(slide, slideSpec.left, 0.75, 1.95, 5.65, 4.75);
      else addBodyText(slide, slideSpec.left || "", 0.75, 1.95, 5.65, 4.75);
      if (Array.isArray(slideSpec.right)) addBullets(slide, slideSpec.right, 6.9, 1.95, 5.65, 4.75);
      else addBodyText(slide, slideSpec.right || "", 6.9, 1.95, 5.65, 4.75);
    } else if (type === "table") {
      addTable(slide, slideSpec.table, 0.65, 1.55, 12.05, 5.25);
    } else if (type === "toc") {
      addItems(slide, slideSpec.items || slideSpec.sections || slideSpec.bullets, 1.15, 1.65, 10.9, 4.75, { badgeColor: palette.accent, titleSize: 15, bodySize: 10 });
    } else if (type === "summary") {
      addItems(slide, slideSpec.items || slideSpec.takeaways || slideSpec.bullets, 1.1, 1.55, 11.1, 4.8, { badgeColor: palette.secondary, titleSize: 14, bodySize: 10.5 });
    } else if (type === "comparison") {
      const leftTitle = slideSpec.leftTitle || slideSpec.aTitle || "A";
      const rightTitle = slideSpec.rightTitle || slideSpec.bTitle || "B";
      slide.addShape(pptx.ShapeType.rect, { x: 0.85, y: 1.55, w: 5.55, h: 5.25, fill: { color: palette.surface }, line: { color: palette.line, width: 0.5 } });
      slide.addShape(pptx.ShapeType.rect, { x: 6.9, y: 1.55, w: 5.55, h: 5.25, fill: { color: palette.surface }, line: { color: palette.line, width: 0.5 } });
      addBodyText(slide, leftTitle, 1.1, 1.8, 5.05, 0.35, { fontSize: 15, color: palette.primary });
      addBodyText(slide, rightTitle, 7.15, 1.8, 5.05, 0.35, { fontSize: 15, color: palette.primary });
      if (Array.isArray(slideSpec.left)) addBullets(slide, slideSpec.left, 1.1, 2.3, 5.05, 4.1, { fontSize: 12.5 });
      else addBodyText(slide, slideSpec.left || "", 1.1, 2.3, 5.05, 4.1, { fontSize: 12.5 });
      if (Array.isArray(slideSpec.right)) addBullets(slide, slideSpec.right, 7.15, 2.3, 5.05, 4.1, { fontSize: 12.5 });
      else addBodyText(slide, slideSpec.right || "", 7.15, 2.3, 5.05, 4.1, { fontSize: 12.5 });
    } else if (type === "timeline" || type === "process") {
      const items = slideSpec.items || slideSpec.steps || [];
      const count = Math.max(1, items.length);
      const startX = 0.95;
      const gap = 0.22;
      const cardW = (11.45 - gap * (count - 1)) / count;
      items.forEach((item, index) => {
        const x = startX + index * (cardW + gap);
        const title = text(typeof item === "string" ? item : item.title || item.label || item.text || "");
        const body = text(typeof item === "string" ? "" : item.body || item.description || "");
        slide.addShape(pptx.ShapeType.rect, { x, y: 2.05, w: cardW, h: 3.6, fill: { color: palette.surface }, line: { color: palette.line, width: 0.5 } });
        slide.addText(String(index + 1), { x: x + 0.18, y: 2.25, w: 0.42, h: 0.3, fontFace: fonts.head, fontSize: 14, bold: true, color: palette.accent, margin: 0 });
        addBodyText(slide, title, x + 0.18, 2.75, cardW - 0.36, 0.55, { fontSize: 13, color: palette.text });
        addBodyText(slide, body, x + 0.18, 3.35, cardW - 0.36, 1.75, { fontSize: 10, color: palette.muted });
      });
    } else if (type === "metrics") {
      const items = slideSpec.items || slideSpec.metrics || [];
      const count = Math.max(1, items.length);
      const cardW = Math.min(3.4, (11.4 - 0.35 * (count - 1)) / count);
      const startX = (13.333 - (cardW * count + 0.35 * (count - 1))) / 2;
      items.forEach((item, index) => {
        const value = text(typeof item === "string" ? item : item.value || item.number || "");
        const label = text(typeof item === "string" ? "" : item.label || item.title || item.text || "");
        const x = startX + index * (cardW + 0.35);
        slide.addShape(pptx.ShapeType.rect, { x, y: 2.1, w: cardW, h: 2.45, fill: { color: palette.surface }, line: { color: palette.line, width: 0.5 } });
        slide.addText(value, { ...fitTextOptions(value, fonts.head, { x: x + 0.2, y: 2.55, w: cardW - 0.4, h: 0.85, fontSize: 34, minFontSize: 16 }), bold: true, color: palette.primary, align: "center", margin: 0.01 });
        addBodyText(slide, label, x + 0.25, 3.58, cardW - 0.5, 0.45, { fontSize: 11, color: palette.muted });
      });
    } else if (type === "image") {
      addImage(slide, slideSpec.image, 0.85, 1.45, 11.65, 5.25);
      if (slideSpec.caption) addBodyText(slide, slideSpec.caption, 0.85, 6.78, 11.65, 0.25, { fontSize: 8.5, color: palette.muted });
    } else if (type === "image_text") {
      addImage(slide, slideSpec.image, 0.85, 1.48, 5.7, 5.2);
      if (Array.isArray(slideSpec.bullets)) addBullets(slide, slideSpec.bullets, 6.95, 1.65, 5.45, 4.9);
      else addBodyText(slide, slideSpec.text || "", 6.95, 1.65, 5.45, 4.9);
    } else if (type === "chart") {
      addChart(slide, slideSpec.chart, 0.85, 1.5, 11.65, 5.25);
    } else if (type === "quote") {
      slide.addText(`"${slideSpec.quote || slideSpec.text || ""}"`, {
        x: 1.3, y: 2.15, w: 10.7, h: 1.2,
        ...fitTextOptions(`"${slideSpec.quote || slideSpec.text || ""}"`, fonts.head, { x: 1.3, y: 2.15, w: 10.7, h: 1.2, fontSize: 25, minFontSize: 13 }),
        italic: true, color: palette.text,
        align: "center", margin: 0.03, fit: "shrink",
      });
      if (slideSpec.attribution) addBodyText(slide, slideSpec.attribution, 2.0, 3.65, 9.4, 0.36, { fontSize: 12, color: palette.muted });
    } else {
      if (Array.isArray(slideSpec.bullets)) addBullets(slide, slideSpec.bullets, 0.9, 1.55, 11.5, 5.25);
      else addBodyText(slide, slideSpec.text || "", 0.85, 1.55, 11.65, 5.25);
    }
  }

  if (Array.isArray(slideSpec.notes) || typeof slideSpec.notes === "string") {
    slide.addNotes(Array.isArray(slideSpec.notes) ? slideSpec.notes.join("\n") : slideSpec.notes);
  }
  addFooter(slide, idx);
  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

(spec.slides || []).forEach((slideSpec, idx) => renderSlide(slideSpec, idx + 1));
if (!spec.slides || spec.slides.length === 0) {
  renderSlide({ type: "title", title: spec.title || "Presentation" }, 1);
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
pptx.writeFile({ fileName: outputPath }).catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
