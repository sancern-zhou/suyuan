export const SCHEMA_VERSION = "1.0";
export const LAYOUT_MODES = new Set(["template", "freeform", "hybrid"]);
export const NATIVE_KINDS = new Set(["chart", "table", "diagram"]);

const STABLE_ID_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;

function isStableId(value) {
  return typeof value === "string" && STABLE_ID_PATTERN.test(value);
}

function duplicates(values) {
  return new Set(values).size !== values.length;
}

export function validateDeck(deck) {
  const errors = [];
  if (!deck?.schemaVersion) {
    errors.push("schemaVersion is required");
  } else if (deck.schemaVersion !== SCHEMA_VERSION) {
    errors.push(`schemaVersion must be ${SCHEMA_VERSION}`);
  }
  if (!deck?.id) {
    errors.push("id is required");
  } else if (!isStableId(deck.id)) {
    errors.push("id must be a stable lowercase identifier");
  }
  if (!deck?.theme) errors.push("theme is required");
  if (!Array.isArray(deck?.slides) || deck.slides.length === 0) {
    errors.push("slides must be a non-empty array");
  } else {
    if (deck.slides.some((slideId) => !isStableId(slideId))) {
      errors.push("slides must contain stable lowercase ids");
    }
    if (duplicates(deck.slides)) {
      errors.push("slides must contain unique stable ids");
    }
  }
  return { ok: errors.length === 0, errors };
}

function validateChart(element, errors) {
  const categories = element?.data?.categories;
  const series = element?.data?.series;
  if (!Array.isArray(categories) || !Array.isArray(series)) {
    errors.push(`chart ${element.id} requires categories and series arrays`);
    return;
  }
  for (const item of series) {
    if (!Array.isArray(item?.values) || item.values.length !== categories.length) {
      errors.push(`chart ${element.id} series ${item?.name || "unnamed"} values must match categories`);
    }
  }
}

export function validateSlide(slide) {
  const errors = [];
  if (!slide?.schemaVersion) {
    errors.push("schemaVersion is required");
  } else if (slide.schemaVersion !== SCHEMA_VERSION) {
    errors.push(`schemaVersion must be ${SCHEMA_VERSION}`);
  }
  if (!slide?.id) {
    errors.push("id is required");
  } else if (!isStableId(slide.id)) {
    errors.push("id must be a stable lowercase identifier");
  }
  if (!slide?.type) errors.push("type is required");
  if (!slide?.intent) errors.push("intent is required");
  if (!LAYOUT_MODES.has(slide?.layoutMode)) {
    errors.push("layoutMode must be template, freeform, or hybrid");
  }
  if (typeof slide?.html !== "string" || slide.html.trim() === "") {
    errors.push("html is required");
  }
  if (!Array.isArray(slide?.nativeElements)) {
    errors.push("nativeElements must be an array");
  } else {
    const ids = slide.nativeElements.map((element) => element?.id).filter(Boolean);
    if (duplicates(ids)) errors.push("nativeElements must contain unique stable ids");
    const checkedPlaceholders = new Set();
    for (const element of slide.nativeElements) {
      if (!isStableId(element?.id)) {
        errors.push("native element id must be a stable lowercase identifier");
        continue;
      }
      if (!NATIVE_KINDS.has(element.kind)) {
        errors.push(`native element ${element.id} has unsupported kind ${element.kind}`);
      }
      if (!checkedPlaceholders.has(element.id)) {
        const doubleQuoted = `data-pptx-ref="${element.id}"`;
        const singleQuoted = `data-pptx-ref='${element.id}'`;
        if (!slide.html.includes(doubleQuoted) && !slide.html.includes(singleQuoted)) {
          errors.push(`native element ${element.id} is missing data-pptx-ref placeholder`);
        }
        checkedPlaceholders.add(element.id);
      }
      if (element.kind === "chart") validateChart(element, errors);
    }
  }
  if (!Array.isArray(slide?.speakerNotes)) errors.push("speakerNotes must be an array");
  return { ok: errors.length === 0, errors };
}
