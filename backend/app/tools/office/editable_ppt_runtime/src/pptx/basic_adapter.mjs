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

function pixels(value, fallback = 0) {
  const number = Number.parseFloat(String(value ?? ""));
  return Number.isFinite(number) ? number : fallback;
}

function lineOptions(style) {
  const color = normalizeColor(style?.borderColor);
  const width = pixels(style?.borderWidth);
  return color && width > 0 ? { color, width: round(width * 0.75) } : { color: "FFFFFF", transparency: 100 };
}

function fillOptions(style) {
  const color = normalizeColor(style?.backgroundColor);
  if (!color) return { color: "FFFFFF", transparency: 100 };
  const opacity = Math.min(1, Math.max(0, Number(style?.opacity ?? 1)));
  return { color, transparency: Math.round((1 - opacity) * 100) };
}

export function addBasicElement(slide, element, pptxApi) {
  if (element.source === "native-ref") return { kind: "native-ref", id: element.id };
  const position = pxBoxToInches(element.box);
  const objectName = element.id;
  const hasText = typeof element.text === "string" && element.text.trim() !== "";
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
    slide.addText(element.text, {
      ...position,
      objectName,
      margin: 0,
      breakLine: false,
      color: normalizeColor(element.style?.color) || "000000",
      fontFace: firstFont(element.style?.fontFamily),
      fontSize: round(pixels(element.style?.fontSize, 16) * 0.75),
      bold: pixels(element.style?.fontWeight, 400) >= 600,
      italic: element.style?.fontStyle === "italic",
      align: ["left", "center", "right", "justify"].includes(element.style?.textAlign)
        ? element.style.textAlign
        : "left",
      valign: "mid",
      fit: "shrink",
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
