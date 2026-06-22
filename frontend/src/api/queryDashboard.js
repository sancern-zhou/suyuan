const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function fetchGuangdongOverview(options = {}) {
  const params = new URLSearchParams()
  if (Array.isArray(options.include) && options.include.length > 0) {
    params.set('include', options.include.join(','))
  }
  if (options.forceRefresh) {
    params.set('force_refresh', 'true')
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
