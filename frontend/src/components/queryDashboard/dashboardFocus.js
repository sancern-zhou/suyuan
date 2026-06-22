const KNOWN_LAYERS = ['city_metrics', 'stations', 'heatmap']

const toList = (value) => {
  if (Array.isArray(value)) return value.filter(Boolean).map(String)
  if (value === null || value === undefined || value === '') return []
  return [String(value)]
}

export const normalizeLayerState = (layerState = {}) => {
  const normalized = {}
  for (const key of KNOWN_LAYERS) {
    normalized[key] = Boolean(layerState?.[key])
  }
  return normalized
}

export const normalizeDashboardFocus = (raw = {}) => {
  const focus = raw && typeof raw === 'object' ? raw : {}
  return {
    scope: focus.scope || 'province',
    cities: toList(focus.cities),
    stations: toList(focus.stations),
    pollutants: toList(focus.pollutants),
    time_range: focus.time_range || null,
    modules: toList(focus.modules),
    layer_state: normalizeLayerState(focus.layer_state),
    source_data_ids: toList(focus.source_data_ids)
  }
}

const focusFromMessage = (message) => {
  if (!message) return null
  const data = message.data || {}
  return data.dashboard_focus ||
    data.metadata?.dashboard_focus ||
    data.result?.dashboard_focus ||
    data.result?.metadata?.dashboard_focus ||
    null
}

export const extractDashboardFocusFromMessages = (messages = []) => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.type !== 'final' && message?.type !== 'tool_result') continue
    const focus = focusFromMessage(message)
    if (focus) return normalizeDashboardFocus(focus)
  }
  return normalizeDashboardFocus()
}
