import { getMessageType } from './messageProcessGrouping.js'

export function formatTrajectoryValue(value) {
  if (value == null) return ''
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function identity(message) {
  const type = getMessageType(message)
  const data = message.data || {}
  const callId = data.tool_use_id || data.tool_call_id
  if (callId && ['tool_use', 'tool_result'].includes(type)) return `${type}:${callId}`
  return message.sequence_number != null ? `sequence:${message.sequence_number}`
    : `${type}:${message.timestamp}:${formatTrajectoryValue(message.content ?? message.content_preview)}`
}

export function mergeTrajectoryMessages(saved = [], live = []) {
  const records = new Map()
  for (const message of [...saved, ...live]) {
    const key = identity(message)
    const previous = records.get(key)
    // Restored chat messages can be abbreviated; preserve the full persisted payload.
    records.set(key, previous ? { ...previous, ...message, data: { ...previous.data, ...message.data }, content: message.content_preview !== undefined ? previous.content ?? message.content : message.content ?? previous.content } : message)
  }
  return [...records.values()].sort((a, b) => {
    if (a.sequence_number != null && b.sequence_number != null) return a.sequence_number - b.sequence_number
    return String(a.timestamp || '').localeCompare(String(b.timestamp || ''))
  })
}

export function buildTrajectoryEntries(messages = []) {
  const entries = []
  let calls = new Map()
  for (const message of messages) {
    const type = getMessageType(message)
    const data = message.data || {}
    if (type === 'user' && !message.steering) calls = new Map()
    const callId = data.tool_use_id || data.tool_call_id
    if (type === 'tool_result' && callId && calls.has(callId)) {
      const entry = calls.get(callId)
      entry.result = data.result ?? data
      entry.status = data.is_error || data.result?.success === false || data.result?.status === 'error' ? '失败' : '已完成'
      entry.completedAt = message.timestamp
      continue
    }
    if (!['user', 'thought', 'tool_use', 'tool_result', 'final', 'error'].includes(type)) continue
    const entry = {
      id: identity(message), type, timestamp: message.timestamp,
      title: { user: '用户', thought: '思考', final: '助手回复', error: '错误' }[type] || data.tool_name || data.tool || '工具调用',
      content: message.content ?? message.content_preview,
      callId, input: data.input ?? data.params ?? data.arguments,
      result: type === 'tool_result' ? data.result ?? data : undefined,
      status: type === 'tool_use' ? '已调用' : type === 'tool_result' ? (data.is_error ? '失败' : '已完成') : ''
    }
    entries.push(entry)
    if (type === 'tool_use' && callId) calls.set(callId, entry)
  }
  return entries
}
