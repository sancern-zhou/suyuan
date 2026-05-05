// Lightweight slide helpers inspired by the OpenAI curated slides workflow.
// They avoid optional native dependencies so the backend can run in the existing environment.
"use strict";

const fs = require("fs");

const DEFAULT_SLIDE = { width: 13.333, height: 7.5 };

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function plainText(value) {
  if (Array.isArray(value)) {
    return value.map((item) => plainText(item && item.text !== undefined ? item.text : item)).join("\n");
  }
  return value === undefined || value === null ? "" : String(value);
}

function estimateLineCount(text, widthIn, fontSizePt) {
  const content = plainText(text);
  if (!content.trim()) return 1;
  const charsPerLine = Math.max(4, Math.floor((widthIn * 72) / Math.max(1, fontSizePt * 0.58)));
  return content
    .split(/\r?\n/)
    .reduce((count, line) => count + Math.max(1, Math.ceil(line.length / charsPerLine)), 0);
}

function calcTextBox(fontSizePt, opts = {}) {
  const lineCount = opts.lines || estimateLineCount(opts.text || "", Number(opts.w) || 1, fontSizePt);
  const leading = Number(opts.leading) || 1.15;
  const padding = Number(opts.padding ?? opts.margin ?? 0.08);
  return {
    w: Number(opts.w) || 0,
    h: (lineCount * fontSizePt * leading) / 72 + padding * 2,
    lines: lineCount,
  };
}

function autoFontSize(text, fontFace, opts = {}) {
  const maxFontSize = Number(opts.maxFontSize ?? opts.fontSize ?? 18);
  const minFontSize = Number(opts.minFontSize ?? 8);
  const width = Number(opts.w) || 1;
  const height = Number(opts.h) || 0.4;
  let chosen = clamp(maxFontSize, minFontSize, maxFontSize);
  for (let size = maxFontSize; size >= minFontSize; size -= 0.5) {
    if (calcTextBox(size, { text, w: width, margin: opts.margin, leading: opts.leading }).h <= height) {
      chosen = size;
      break;
    }
  }
  return { ...opts, fontFace, fontSize: Number(chosen.toFixed(1)), fit: "shrink" };
}

function readPngSize(buffer) {
  if (
    buffer.length >= 24 &&
    buffer[0] === 0x89 &&
    buffer[1] === 0x50 &&
    buffer[2] === 0x4e &&
    buffer[3] === 0x47
  ) {
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }
  return null;
}

function readJpegSize(buffer) {
  if (buffer.length < 4 || buffer[0] !== 0xff || buffer[1] !== 0xd8) return null;
  let offset = 2;
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xff) return null;
    const marker = buffer[offset + 1];
    const length = buffer.readUInt16BE(offset + 2);
    if (marker >= 0xc0 && marker <= 0xc3) {
      return { width: buffer.readUInt16BE(offset + 7), height: buffer.readUInt16BE(offset + 5) };
    }
    offset += 2 + length;
  }
  return null;
}

function getImageDimensions(source) {
  if (!source || !fs.existsSync(source)) return null;
  const buffer = fs.readFileSync(source);
  return readPngSize(buffer) || readJpegSize(buffer);
}

function imageSizingContain(source, x, y, w, h) {
  const dimensions = getImageDimensions(source);
  if (!dimensions || !dimensions.width || !dimensions.height) return { x, y, w, h };
  const imageRatio = dimensions.width / dimensions.height;
  const boxRatio = w / h;
  if (imageRatio > boxRatio) {
    const fittedH = w / imageRatio;
    return { x, y: y + (h - fittedH) / 2, w, h: fittedH };
  }
  const fittedW = h * imageRatio;
  return { x: x + (w - fittedW) / 2, y, w: fittedW, h };
}

function imageSizingCrop(source, x, y, w, h) {
  return { x, y, w, h, sizingCrop: true };
}

function getSlideDimensions(pptx) {
  const layout = pptx && pptx._layouts && pptx._layouts[pptx.layout];
  if (layout && layout.width && layout.height) return { width: layout.width, height: layout.height };
  return DEFAULT_SLIDE;
}

function warnIfSlideElementsOutOfBounds(slide, pptx) {
  if (!slide || !Array.isArray(slide._slideObjects)) return;
  const dims = getSlideDimensions(pptx);
  slide._slideObjects.forEach((obj, index) => {
    const data = obj.data || obj.options || {};
    const x = Number(data.x || 0);
    const y = Number(data.y || 0);
    const w = Number(data.w || 0);
    const h = Number(data.h || 0);
    if (x < -0.01 || y < -0.01 || x + w > dims.width + 0.01 || y + h > dims.height + 0.01) {
      console.warn(`Slide element out of bounds: element=${index} x=${x} y=${y} w=${w} h=${h}`);
    }
  });
}

function warnIfSlideHasOverlaps(slide) {
  if (!slide || !Array.isArray(slide._slideObjects)) return;
  const boxes = slide._slideObjects
    .map((obj, index) => {
      const data = obj.data || obj.options || {};
      return {
        index,
        type: obj.type || "unknown",
        x: Number(data.x || 0),
        y: Number(data.y || 0),
        w: Number(data.w || 0),
        h: Number(data.h || 0),
      };
    })
    .filter((box) => box.w > 0 && box.h > 0);

  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      const overlapW = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const overlapH = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (overlapW > 0.12 && overlapH > 0.12 && (a.type === "text" || b.type === "text")) {
        console.warn(`Possible text overlap: element=${a.index} with element=${b.index}`);
      }
    }
  }
}

module.exports = {
  autoFontSize,
  calcTextBox,
  imageSizingContain,
  imageSizingCrop,
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
};
