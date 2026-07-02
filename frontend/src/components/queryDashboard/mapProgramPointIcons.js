export const DEFAULT_POINT_ICON = 'station'

export const POINT_ICON_PRESETS = Object.freeze([
  DEFAULT_POINT_ICON,
  'pollution_source',
  'factory',
  'dust',
  'traffic',
  'fire',
  'monitor',
  'selected'
])

const POINT_ICON_SET = new Set(POINT_ICON_PRESETS)

const normalizeIcon = (icon) => {
  if (typeof icon !== 'string') return null
  const value = icon.trim()
  return POINT_ICON_SET.has(value) ? value : null
}

export function resolvePointIconPreset(style = {}, properties = {}) {
  const iconBy = typeof style.icon_by === 'string' ? style.icon_by : null
  const iconMap = style.icon_map && typeof style.icon_map === 'object' ? style.icon_map : null

  if (iconBy && iconMap && Object.prototype.hasOwnProperty.call(properties, iconBy)) {
    const mappedIcon = normalizeIcon(iconMap[String(properties[iconBy])])
    if (mappedIcon) return mappedIcon
  }

  return normalizeIcon(style.icon) ||
    normalizeIcon(style.default_icon) ||
    DEFAULT_POINT_ICON
}

export function pointIconClassName(icon) {
  return normalizeIcon(icon) || DEFAULT_POINT_ICON
}
