const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function fetchGuangdongOverview(options = {}) {
  const params = new URLSearchParams()
  if (Array.isArray(options.include) && options.include.length > 0) {
    params.set('include', options.include.join(','))
  }
  const query = params.toString()
  const response = await fetch(`${API_BASE_URL}/query-dashboard/guangdong-overview${query ? `?${query}` : ''}`, {
    cache: 'no-store'
  })
  if (!response.ok) {
    throw new Error(`广东总览数据加载失败：${response.status}`)
  }
  return await response.json()
}

export async function fetchMapDataFeatures(dataId, options = {}) {
  const params = new URLSearchParams()
  if (options.lon) params.set('lon', options.lon)
  if (options.lat) params.set('lat', options.lat)
  if (options.view) params.set('view', options.view)
  if (options.limit) params.set('limit', String(options.limit))
  const query = params.toString()
  const response = await fetch(`${API_BASE_URL}/query-dashboard/map-data/${encodeURIComponent(dataId)}${query ? `?${query}` : ''}`, {
    cache: 'no-store'
  })
  if (!response.ok) {
    throw new Error(`地图图层数据加载失败：${response.status}`)
  }
  return await response.json()
}
