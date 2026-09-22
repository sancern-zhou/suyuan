import { authFetch } from '@/auth/http.js'
import { parseFinalSseData, parseSseChunk } from './workflowSse.js'

export { parseSseChunk } from './workflowSse.js'

const workflowBase = sessionId => `/api/sessions/${encodeURIComponent(sessionId)}/workflows`

async function readJson(response, fallback) {
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : detail?.message
    throw new Error(message || `${fallback}（HTTP ${response.status}）`)
  }
  return payload
}

export async function listSessionWorkflows(sessionId) {
  if (!sessionId) return { workflows: [], total: 0 }
  return readJson(await authFetch(workflowBase(sessionId)), '工作流列表加载失败')
}

export async function getSessionWorkflow(sessionId, workflowId) {
  return readJson(
    await authFetch(`${workflowBase(sessionId)}/${encodeURIComponent(workflowId)}`),
    '工作流详情加载失败'
  )
}

export async function getSessionWorkflowEvents(sessionId, workflowId, { after = 0, eventId = '0-0' } = {}) {
  const params = new URLSearchParams({ after: String(after), event_id: eventId })
  return readJson(
    await authFetch(`${workflowBase(sessionId)}/${encodeURIComponent(workflowId)}/events?${params}`),
    '工作流事件加载失败'
  )
}

export async function cancelSessionWorkflow(sessionId, workflowId) {
  return readJson(
    await authFetch(`${workflowBase(sessionId)}/${encodeURIComponent(workflowId)}/cancel`, { method: 'POST' }),
    '工作流取消失败'
  )
}

export async function resumeSessionWorkflow(sessionId, workflowId) {
  return readJson(
    await authFetch(`${workflowBase(sessionId)}/${encodeURIComponent(workflowId)}/resume`, { method: 'POST' }),
    '工作流恢复失败'
  )
}

export async function followSessionWorkflow(sessionId, workflowId, {
  afterEventId = '0-0',
  timeoutSeconds = 30,
  signal,
  onEvent
} = {}) {
  const params = new URLSearchParams({
    follow: 'true',
    event_id: afterEventId,
    timeout_seconds: String(timeoutSeconds)
  })
  const response = await authFetch(
    `${workflowBase(sessionId)}/${encodeURIComponent(workflowId)}/events?${params}`,
    { signal }
  )
  if (!response.ok) {
    await readJson(response, '工作流事件流连接失败')
    return
  }
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    if (buffer) {
      const parsed = parseSseChunk(buffer, data => {
        try { onEvent?.(JSON.parse(data)) } catch { /* Ignore malformed server events. */ }
      })
      buffer = parsed.remainder
    }
    if (done) break
  }
  if (buffer.trim()) {
    const data = parseFinalSseData(buffer)
    try { onEvent?.(JSON.parse(data)) } catch { /* Ignore incomplete events. */ }
  }
}
