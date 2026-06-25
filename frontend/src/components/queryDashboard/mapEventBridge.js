const randomId = () => Math.random().toString(36).slice(2, 10)

function normalizePoint(point) {
  if (!point) return null
  if (Array.isArray(point) && point.length >= 2) return [point[0], point[1]]
  if (typeof point.getLng === 'function' && typeof point.getLat === 'function') {
    return [point.getLng(), point.getLat()]
  }
  if (typeof point.lng === 'number' && typeof point.lat === 'number') return [point.lng, point.lat]
  return point
}

function normalizeBounds(bounds) {
  if (!bounds) return null
  if (Array.isArray(bounds)) return bounds
  if (typeof bounds.getSouthWest === 'function' && typeof bounds.getNorthEast === 'function') {
    return {
      southWest: normalizePoint(bounds.getSouthWest()),
      northEast: normalizePoint(bounds.getNorthEast())
    }
  }
  return bounds
}

export function summarizeMapView(mapLike) {
  if (!mapLike) return {}
  const center = typeof mapLike.getCenter === 'function' ? mapLike.getCenter() : mapLike.center
  const zoom = typeof mapLike.getZoom === 'function' ? mapLike.getZoom() : mapLike.zoom
  const bounds = typeof mapLike.getBounds === 'function' ? mapLike.getBounds() : mapLike.bounds
  return {
    ...(center ? { center: normalizePoint(center) } : {}),
    ...(zoom !== undefined ? { zoom } : {}),
    ...(bounds ? { bounds: normalizeBounds(bounds) } : {})
  }
}

export function createMapEvent(event, options = {}) {
  const now = options.now || (() => new Date())
  return {
    type: 'map_event',
    event_id: options.eventId || `mapevt_${Date.now()}_${randomId()}`,
    event,
    session_id: options.sessionId || null,
    turn_id: options.turnId || null,
    ...(options.geometry ? { geometry: options.geometry } : {}),
    ...(options.feature ? { feature: options.feature } : {}),
    ...(options.receipt ? { receipt: options.receipt } : {}),
    active_layers: Array.isArray(options.activeLayers) ? options.activeLayers : [],
    map_view: options.mapView || {},
    timestamp: now().toISOString()
  }
}
