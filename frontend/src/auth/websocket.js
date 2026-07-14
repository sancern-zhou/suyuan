import { authFetch } from './http.js'


function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


export async function connectScheduledTaskWebSocket({
  authFetch: fetchImpl = authFetch,
  WebSocketImpl = globalThis.WebSocket,
  location = globalThis.window.location,
  apiBaseUrl = configuredApiBase()
} = {}) {
  const response = await fetchImpl('/api/auth/ws-ticket', { method: 'POST' })
  if (!response.ok) throw new Error(`WebSocket ticket request failed: ${response.status}`)
  const payload = await response.json()
  if (!payload.ticket) throw new Error('WebSocket ticket response is missing a ticket')
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const base = apiBaseUrl.replace(/\/$/, '')
  const url = `${protocol}//${location.host}${base}/ws/scheduled-tasks?ticket=${encodeURIComponent(payload.ticket)}`
  return new WebSocketImpl(url)
}
