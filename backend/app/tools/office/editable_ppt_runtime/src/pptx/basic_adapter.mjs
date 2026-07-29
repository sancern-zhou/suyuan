const SLIDE_WIDTH_PX = 1440;
const SLIDE_HEIGHT_PX = 810;
const SLIDE_WIDTH_IN = 13.333;
const SLIDE_HEIGHT_IN = 7.5;

function round(value) {
  return Math.round(value * 10_000) / 10_000;
}

export function pxBoxToInches(box) {
  return {
    x: round((box.x / SLIDE_WIDTH_PX) * SLIDE_WIDTH_IN),
    y: round((box.y / SLIDE_HEIGHT_PX) * SLIDE_HEIGHT_IN),
    w: round((box.width / SLIDE_WIDTH_PX) * SLIDE_WIDTH_IN),
    h: round((box.height / SLIDE_HEIGHT_PX) * SLIDE_HEIGHT_IN),
  };
}

export function normalizeColor(value) {
  if (!value || value === "transparent") return null;
  const hex = String(value).trim().match(/^#([0-9a-f]{6})$/i);
  if (hex) return hex[1].toUpperCase();
  const rgb = String(value).match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)$/i);
  if (!rgb || (rgb[4] !== undefined && Number(rgb[4]) === 0)) return null;
  return rgb
    .slice(1, 4)
    .map((part) => Number(part).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function firstFont(fontFamily) {
  return String(fontFamily || "Arial")
    .split(",")[0]
    .trim()
    .replace(/^['"]|['"]$/g, "");
}

export function powerpointFont(theme = {}, role = "body") {
  const title = role === "title";
  const previewFont = title ? theme.fontTitle : theme.fontBody;
  const configured = title ? theme.pptFontTitle : theme.pptFontBody;
  return configured || (previewFont === "Noto Sans CJK SC" ? "Microsoft YaHei" : previewFont) || "Microsoft YaHei";
}

function mappedFont(fontFamily, element, theme) {
  const measured = firstFont(fontFamily);
  const title = ["h1", "h2"].includes(element.tagName);
  const previewThemeFont = title ? theme?.fontTitle : theme?.fontBody;
  if (!measured || measured === "Noto Sans CJK SC" || measured === previewThemeFont) {
    return powerpointFont(theme, title ? "title" : "body");
  }
  return measured;
}

function textPosition(element) {
  const position = pxBoxToInches(element.box);
  if (!["h1", "h2"].includes(element.tagName)) return position;
  const rightMargin = 0.65;
  return {
    ...position,
    w: Math.max(position.w, round(SLIDE_WIDTH_IN - position.x - rightMargin)),
  };
}

function pixels(value, fallback = 0) {
  const number = Number.parseFloat(String(value ?? ""));
  return Number.isFinite(number) ? number : fallback;
}

function colorAlpha(value) {
  const rgba = String(value || "").match(
    /^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*([\d.]+))?\s*\)$/i,
  );
  if (!rgba) return normalizeColor(value) ? 1 : 0;
  return rgba[1] === undefined ? 1 : Math.min(1, Math.max(0, Number(rgba[1])));
}

function lineOptions(style) {
  const color = normalizeColor(style?.borderColor);
  const width = pixels(style?.borderWidth);
  const alpha = colorAlpha(style?.borderColor);
  return color && width > 0 && alpha > 0
    ? { color, width: round(width * 0.75), transparency: Math.round((1 - alpha) * 100) }
    : { color: "FFFFFF", transparency: 100 };
}

function fillOptions(style) {
  const color = normalizeColor(style?.backgroundColor);
  if (!color) return { color: "FFFFFF", transparency: 100 };
  const opacity = Math.min(1, Math.max(0, Number(style?.opacity ?? 1)));
  const alpha = colorAlpha(style?.backgroundColor);
  return { color, transparency: Math.round((1 - opacity * alpha) * 100) };
}

export function addBasicElement(slide, element, pptxApi, theme = {}) {
  if (element.source === "native-ref") return { kind: "native-ref", id: element.id };
  const position = textPosition(element);
  const objectName = element.id;
  const hasRichText = Array.isArray(element.textRuns) && element.textRuns.length > 0;
  const hasText = typeof element.text === "string" && element.text.trim() !== "" &&
    (!element.hasTaggedDescendant || hasRichText);
  const background = normalizeColor(element.style?.backgroundColor);

  if (element.tagName === "img" && element.src) {
    slide.addImage({ path: element.src, ...position, objectName });
    return { kind: "image", id: element.id };
  }
  if (background) {
    const rounded = pixels(element.style?.borderRadius) > 0;
    slide.addShape(rounded ? pptxApi.ShapeType.roundRect : pptxApi.ShapeType.rect, {
      ...position,
      objectName: hasText ? `${objectName}-background` : objectName,
      fill: fillOptions(element.style),
      line: lineOptions(element.style),
      radius: rounded ? pixels(element.style?.borderRadius) : undefined,
    });
  }
  if (hasText) {
    const text = hasRichText
      ? element.textRuns.map((run) => ({
          text: run.text,
          options: {
            color: normalizeColor(run.style?.color) || normalizeColor(element.style?.color) || "000000",
            fontFace: mappedFont(run.style?.fontFamily || element.style?.fontFamily, element, theme),
            fontSize: round(pixels(run.style?.fontSize || element.style?.fontSize, 16) * 0.75),
            bold: pixels(run.style?.fontWeight, pixels(element.style?.fontWeight, 400)) >= 600,
            italic: (run.style?.fontStyle || element.style?.fontStyle) === "italic",
          },
        }))
      : element.text;
    slide.addText(text, {
      ...position,
      objectName,
      margin: 0,
      breakLine: false,
      color: normalizeColor(element.style?.color) || "000000",
      fontFace: mappedFont(element.style?.fontFamily, element, theme),
      fontSize: round(pixels(element.style?.fontSize, 16) * 0.75),
      bold: pixels(element.style?.fontWeight, 400) >= 600,
      italic: element.style?.fontStyle === "italic",
      align: ["left", "center", "right", "justify"].includes(element.style?.textAlign)
        ? element.style.textAlign
        : "left",
      valign: "mid",
      fit: "shrink",
      wrap: !["h1", "h2"].includes(element.tagName),
      line: { color: "FFFFFF", transparency: 100 },
      fill: { color: "FFFFFF", transparency: 100 },
    });
    return { kind: "text", id: element.id };
  }
  if (!background) {
    slide.addShape(pptxApi.ShapeType.rect, {
      ...position,
      objectName,
      fill: { color: "FFFFFF", transparency: 100 },
      line: lineOptions(element.style),
    });
  }
  return { kind: "shape", id: element.id };
}

export async function loadDomToPptxNodeAdapter() {
  return import("dom-to-pptx/node");
}
