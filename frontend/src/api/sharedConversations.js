import { authFetch } from '@/auth/http.js'

/**
 * 共享对话面板 API
 */
const API_BASE_URL = ((import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/shared-conversations`

async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }
  if (method !== 'GET' && method !== 'HEAD' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const response = await authFetch(url, { ...options, method, headers })
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) {
    throw new Error(data.detail || `请求失败（${response.status}）`)
  }
  return data
}

export async function listSharedConversations(options = {}) {
  const { search = '', limit = 50, offset = 0 } = options
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return await request(`${BASE_URL}/?${params.toString()}`)
}

export async function getSharedConversation(shareId) {
  return await request(`${BASE_URL}/${encodeURIComponent(shareId)}`)
}

export async function shareConversation(sessionId) {
  return await request(`${BASE_URL}/`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId })
  })
}

export async function deleteSharedConversation(shareId) {
  return await request(`${BASE_URL}/${encodeURIComponent(shareId)}`, { method: 'DELETE' })
}
