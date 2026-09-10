import { authFetch } from '../auth/http'

const BASE = '/api/jiangsu/smart-events'

function queryString(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach(item => query.append(key, item))
    else if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

async function parse(response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail?.message || payload?.detail || '智能事件接口请求失败')
  return payload
}

export async function listJiangsuSmartEvents(params = {}) {
  return parse(await authFetch(`${BASE}${queryString(params)}`))
}

export async function getJiangsuSmartEvent(eventId, params = {}) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}${queryString(params)}`))
}

export async function collectJiangsuSmartEventEvidence(eventId) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/evidence`, { method: 'POST' }))
}

export async function getJiangsuSmartEventConfig() {
  return parse(await authFetch(`${BASE}/config/current`))
}

export async function saveJiangsuSmartEventConfig(values) {
  return parse(await authFetch(`${BASE}/config/current`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  }))
}

export async function syncJiangsuSmartEvents(params = {}) {
  return parse(await authFetch(`${BASE}/sync${queryString(params)}`, { method: 'POST' }))
}

export async function listJiangsuSmartEventTasks(params = {}) {
  return parse(await authFetch(`${BASE}/tasks${queryString(params)}`))
}

export async function getJiangsuSmartEventTask(taskId) {
  return parse(await authFetch(`${BASE}/tasks/${encodeURIComponent(taskId)}`))
}

export async function createJiangsuSmartEventTask(eventId, conversationId) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(conversationId ? { conversation_id: conversationId } : {}),
  }))
}

export async function dispatchJiangsuSmartEventAiJudgment(eventId) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/ai-dispatch`, {
    method: 'POST',
  }))
}

export async function dispatchJiangsuSmartEventOrder(eventId, order) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/dispatch-order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(order),
  }))
}

export async function submitJiangsuSmartEventFeedback(eventId, feedback, attachments = []) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback, attachments }),
  }))
}

export async function submitJiangsuSmartEventJudgment(eventId, judgment) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/ai-judgments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(judgment),
  }))
}

export async function recordJiangsuSmartEventOperation(eventId, operation) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/operations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(operation),
  }))
}

export async function archiveJiangsuSmartEvent(eventId, comment = '', confirmation = null) {
  const body = confirmation
    ? { comment: comment || null, ...confirmation }
    : { comment: comment || null }
  return parse(await authFetch(`${BASE}/${encodeURIComponent(eventId)}/archive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}
