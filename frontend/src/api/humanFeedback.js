import { authFetch } from '@/auth/http.js'

const API_BASE_URL = ((import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api').replace(/\/$/, '')

export async function submitHumanFeedback(sessionId, payload) {
  if (!sessionId) throw new Error('human_feedback_session_required')
  const response = await authFetch(
    `${API_BASE_URL}/agent/${encodeURIComponent(sessionId)}/human-feedback`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }
  )
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `human_feedback_failed_${response.status}`)
  }
  return response.json()
}
