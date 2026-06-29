const DASHBOARD_LAYER_IDS = new Set(['city_metrics', 'stations', 'heatmap'])

export const normalizeLayerState = (layerState = {}) => {
  const normalized = {}
  for (const key of DASHBOARD_LAYER_IDS) {
    normalized[key] = Boolean(layerState?.[key])
  }
  return normalized
}

export function layerStateFromMapProgram(mapProgram) {
  const dashboardLayers = Array.isArray(mapProgram?.state?.dashboard_layers)
    ? mapProgram.state.dashboard_layers
    : []

  if (!dashboardLayers.length) return null

  const layerState = normalizeLayerState()
  dashboardLayers.forEach(layer => {
    if (DASHBOARD_LAYER_IDS.has(layer?.id)) {
      layerState[layer.id] = Boolean(layer.visible)
    }
  })

  return layerState
}
