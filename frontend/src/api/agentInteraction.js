import { authFetch } from '@/auth/http.js'

const API_BASE_URL = ((import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api').replace(/\/$/, '')

export async function resolveAgentInteraction(sessionId, interactionId, payload) {
  const response = await authFetch(
    `${API_BASE_URL}/agent/${encodeURIComponent(sessionId)}/interactions/${encodeURIComponent(interactionId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }
  )
  if (!response.ok) throw new Error(await response.text() || `interaction_resolution_failed_${response.status}`)
  return response.json()
}
