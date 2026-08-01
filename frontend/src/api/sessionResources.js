import { authFetch } from '../auth/http.js'

const API_BASE_URL = ((import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/sessions`

const request = async (url, options = {}) => {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }
  if (method !== 'GET' && method !== 'HEAD' && options.body != null) {
    headers['Content-Type'] = 'application/json'
  }
  const response = await authFetch(url, { ...options, method, headers })
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `HTTP error! status: ${response.status}`)
  }
  return response.status === 204 ? null : response.json()
}

export const buildResourceQuery = (filters = {}) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  return params.toString()
}

export const listSessionResources = (sessionId, filters = {}) => {
  const query = buildResourceQuery(filters)
  const url = `${BASE_URL}/${encodeURIComponent(sessionId)}/resources`
  return request(query ? `${url}?${query}` : url)
}

export const resourceContentUrl = (sessionId, resourceId, { directory = false } = {}) => (
  `${BASE_URL}/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(resourceId)}/content${directory ? '/' : ''}`
)

export const resourceDownloadUrl = (sessionId, resourceId) => (
  `${resourceContentUrl(sessionId, resourceId)}?disposition=attachment`
)

export const invokeResourceAction = (actionUrl, payload = {}) => request(actionUrl, {
  method: 'POST',
  body: JSON.stringify(payload)
})
