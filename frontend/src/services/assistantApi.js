import { authFetch } from '../auth/http.js'
import { accountGeneration, assertAccountGeneration } from '../auth/accountSession.js'

const base = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function request(path, body) {
  const epoch = accountGeneration()
  const response = await authFetch(`${base}/assistant/${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  } : {})
  const data = await response.json()
  assertAccountGeneration(epoch)
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : '助理操作失败，请刷新后重试'
    throw new Error(response.status === 409 ? '事项已变化，请刷新后重试' : detail)
  }
  return data
}

export const listAssistantItems = (tab, offset = 0) => {
  const path = { tasks: 'tasks', suggestions: 'suggestions' }[tab]
  if (!path) throw new Error('未知助理视图')
  return request(`${path}?limit=20&offset=${offset}${tab === 'suggestions' ? '&state=all' : ''}`)
}
export const getAssistantTask = id => request(`tasks/${encodeURIComponent(id)}`)
export const changeAssistantTask = (item, action, text = '') => request(
  `tasks/${encodeURIComponent(item.task_id)}/actions`, { action, text, expected_version: item.version }
)
export const decideAssistantSuggestion = (item, action) => request(
  `suggestions/${encodeURIComponent(item.suggestion_id)}/actions`, { action, expected_version: item.version }
)
export const listAssistantConversations = () => request('conversations?limit=200')
export const syncAssistantConversation = (id, revision) => request(
  `conversations/${encodeURIComponent(id)}/sync${revision == null ? '' : `?revision=${revision}`}`
)
export const readAssistantConversation = (id, throughSequence) => request(
  `conversations/${encodeURIComponent(id)}/read`, { through_sequence: throughSequence }
)
