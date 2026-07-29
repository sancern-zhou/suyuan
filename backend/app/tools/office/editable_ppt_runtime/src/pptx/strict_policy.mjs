const ALLOWED_RASTER_ASSET_KINDS = new Set([
  "user-photo",
  "retrieved-image",
  "generated-image",
  "brand-raster",
]);

export class EditablePolicyError extends Error {
  constructor(code, element, message) {
    super(message);
    this.name = "EditablePolicyError";
    this.code = code;
    this.elementId = element?.id || null;
  }
}

export function isAllowedRaster(element) {
  return element?.kind === "image" && ALLOWED_RASTER_ASSET_KINDS.has(element?.assetKind);
}

export function assertEditable(element, mode = "strict") {
  if (mode !== "strict" || element?.fallback !== "png") return;
  if (isAllowedRaster(element)) return;
  throw new EditablePolicyError(
    "RASTER_FALLBACK_FORBIDDEN",
    element,
    `strict editability forbids raster fallback for ${element?.id || element?.kind || "element"}`,
  );
}

export function auditFallbacks(elements, mode = "strict") {
  let allowedRasterFallbacks = 0;
  const forbiddenElementIds = [];
  for (const element of elements || []) {
    if (element?.fallback !== "png") continue;
    if (isAllowedRaster(element)) {
      allowedRasterFallbacks += 1;
      continue;
    }
    if (mode === "strict") forbiddenElementIds.push(element?.id || null);
  }
  return {
    allowedRasterFallbacks,
    forbiddenRasterFallbacks: forbiddenElementIds.length,
    forbiddenElementIds,
  };
}
