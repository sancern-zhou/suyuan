import { authFetch } from '@/auth/http.js'

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * 拉取大屏整屏快照；携带 If-None-Match 时未变化返回 304。
 * @returns {{notModified: true} | {notModified: false, data: object, etag: string|null}}
 */
export async function fetchScreenSnapshot(etag) {
  const headers = {}
  if (etag) headers['If-None-Match'] = etag
  const response = await authFetch(
    `${API_BASE_URL}/xuchang-dashboard/screen-snapshot`,
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
