import { authFetch } from '@/auth/http.js'
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function fetchMapDataFeatures(filePath, options = {}) {
  const params = new URLSearchParams()
  if (options.lon) params.set('lon', options.lon)
  if (options.lat) params.set('lat', options.lat)
  if (options.view) params.set('view', options.view)
  if (options.limit) params.set('limit', String(options.limit))
  params.set('file_path', filePath)
  const response = await authFetch(`${API_BASE_URL}/query-dashboard/map-data?${params.toString()}`, {
    cache: 'no-store'
  })
  if (!response.ok) {
    throw new Error(`地图图层数据加载失败：${response.status}`)
  }
  return await response.json()
}
