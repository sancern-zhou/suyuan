const RADAR_INCOMPATIBLE_COMPONENTS = [
  'grid',
  'xAxis',
  'yAxis',
  'dataZoom'
]

export const isRadarOption = (option) => {
  if (!option || typeof option !== 'object') {
    return false
  }

  const series = Array.isArray(option.series) ? option.series : [option.series]
  const hasRadarSeries = series.some(item => item?.type === 'radar')
  const hasNestedRadar = isRadarOption(option.baseOption) ||
    (Array.isArray(option.options) && option.options.some(isRadarOption))
  return (Boolean(option.radar) && hasRadarSeries) || hasNestedRadar
}

export const cloneEChartsOption = (value) => {
  if (Array.isArray(value)) {
    return value.map(cloneEChartsOption)
  }

  if (!value || typeof value !== 'object') {
    return value
  }

  const cloned = {}
  Object.keys(value).forEach(key => {
    cloned[key] = cloneEChartsOption(value[key])
  })
  return cloned
}

// Older saved chart options may have several named series but no legend.
export const ensureEChartsLegend = (option) => {
  if (!option || typeof option !== 'object' || 'legend' in option ||
      !('xAxis' in option) || !('yAxis' in option) || !Array.isArray(option.series)) {
    return option
  }
  const names = [...new Set(option.series
    .map(series => series?.name)
    .filter(name => typeof name === 'string' && name.trim()))]
  if (names.length < 2) return option

  option.legend = { data: names, orient: 'horizontal', bottom: 35 }
  if (!option.grid) option.grid = { bottom: 84, containLabel: true }
  return option
}

const sanitizeRadarOptionLayer = (option) => {
  if (!option || typeof option !== 'object') {
    return option
  }

  const sanitized = { ...option }
  RADAR_INCOMPATIBLE_COMPONENTS.forEach(component => {
    delete sanitized[component]
  })
  return sanitized
}

export const sanitizeCompleteRadarOption = (option) => {
  if (!isRadarOption(option)) {
    return option
  }

  const sanitized = sanitizeRadarOptionLayer(option)
  if (sanitized.baseOption) {
    sanitized.baseOption = sanitizeCompleteRadarOption(sanitized.baseOption)
  }
  if (Array.isArray(sanitized.options)) {
    sanitized.options = sanitized.options.map(sanitizeCompleteRadarOption)
  }
  return sanitized
}
