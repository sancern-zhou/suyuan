import { authFetch } from '@/auth/http.js'

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

// 大屏直连令牌：/bigscreen?access_token=... 场景下，页面 URL 携带的令牌
// 透传给所有 dashboard API 请求（后端 XUCHANG_DASHBOARD_ACCESS_TOKEN 校验）。
// 只在进入页面时读取一次，避免快照/素材 URL 回显之外的位置泄漏。
let dashboardAccessToken = ''

export function initDashboardAccessToken(search = window.location.search) {
  const params = new URLSearchParams(search)
  dashboardAccessToken = params.get('access_token') || ''
  return dashboardAccessToken
}

function dashboardUrl(path, params = {}) {
  const query = new URLSearchParams(params)
  if (dashboardAccessToken) query.set('access_token', dashboardAccessToken)
  const qs = query.toString()
  return `${API_BASE_URL}${path}${qs ? `?${qs}` : ''}`
}

/**
 * 大屏素材出网地址（传输轨迹 / GEMS 卫星图），走鉴权资产路由。
 */
export function dashboardAssetUrl(assetPath) {
  if (!assetPath) return ''
  return dashboardUrl('/xuchang-dashboard/asset', { path: assetPath })
}

/**
 * 拉取大屏整屏快照；携带 If-None-Match 时未变化返回 304。
 * @returns {{notModified: true} | {notModified: false, data: object, etag: string|null}}
 */
export async function fetchScreenSnapshot(etag) {
  const headers = {}
  if (etag) headers['If-None-Match'] = etag
  const response = await authFetch(
    dashboardUrl('/xuchang-dashboard/screen-snapshot'),
    { headers, cache: 'no-store' }
  )
  if (response.status === 304) return { notModified: true }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail || payload?.message
    throw new Error(typeof detail === 'string' ? detail : `大屏快照加载失败（HTTP ${response.status}）`)
  }
  return {
    notModified: false,
    data: await response.json(),
    etag: response.headers.get('ETag')
  }
}
