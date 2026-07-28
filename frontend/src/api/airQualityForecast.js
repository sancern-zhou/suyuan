import { authFetch } from '@/auth/http.js'

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function fetchXuchangHourlyForecast() {
  const response = await authFetch(`${API_BASE_URL}/air-quality-forecast/xuchang-hourly`, {
    cache: 'no-store'
  })
  if (!response.ok) throw new Error(`预报数据加载失败：${response.status}`)
  return await response.json()
}
