export const CONVERSATION_LIST_VIEW = Object.freeze({
  RECENT: 'recent',
  CASES: 'cases',
  IM: 'im'
})

export function isScheduledConversation(session = {}) {
  return String(session.session_id || '').startsWith('scheduled_task_')
}

export function filterConversationHistory(sessions = []) {
  return sessions.filter(session => !isScheduledConversation(session))
}

export function reconcileConversationHistoryStats(stats, visibleSessions = []) {
  if (!stats) return stats
  return { ...stats, total: visibleSessions.length }
}

export function filterSidebarConversations(sessions = [], view = CONVERSATION_LIST_VIEW.RECENT) {
  const visible = filterConversationHistory(sessions)

  if (view === CONVERSATION_LIST_VIEW.CASES) {
    return visible.filter(session => session?.metadata?.is_case === true)
  }
  if (view === CONVERSATION_LIST_VIEW.IM) {
    return visible.filter(session => session?.source === 'social')
  }
  return visible.filter(session => session?.source !== 'social')
}

export function toggleConversationListView(currentView, targetView) {
  return currentView === targetView ? CONVERSATION_LIST_VIEW.RECENT : targetView
}

// 会话列表排序只能基于服务端持久化的 updated_at（UTC）。客户端消息
// timestamp 可能是本地时间或运行期事件时间，混用会把旧会话顶到最前。
//
// 服务端返回的无时区时间（如 "2026-11-17T08:53:14"）是 UTC，浏览器会按
// 本地时区解析，导致与带 Z 的运行期时间比较时整体偏移 8 小时。这里统一
// 约定：无时区字符串按 UTC 解析，显式带时区的按其自身偏移解析。
export function parseConversationTimestamp(value) {
  if (!value) return 0
  if (value instanceof Date) {
    const time = value.getTime()
    return Number.isFinite(time) ? time : 0
  }
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const raw = String(value).trim()
  if (!raw) return 0
  const hasTimezone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(raw)
  const normalized = hasTimezone ? raw : `${raw}Z`
  const time = new Date(normalized).getTime()
  return Number.isFinite(time) ? time : 0
}

export function conversationRecency(session = {}) {
  return parseConversationTimestamp(session?.updated_at)
}

// 消息 timestamp 与 catalog/sessions 的 updated_at 不同源：
// - 运行期新消息是带 Z 的 UTC ISO（reactStore `_addMessageToState`）
// - 从库恢复的消息是无时区本地时间（session_messages.timestamp 存 CST）
// 所以无时区消息时间必须按 +08:00 解析，不能当 UTC。
export function parseMessageTimestamp(value) {
  if (!value || typeof value !== 'string') return parseConversationTimestamp(value)
  const raw = value.trim()
  if (!raw) return 0
  if (/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(raw)) return parseConversationTimestamp(raw)
  return parseConversationTimestamp(`${raw}+08:00`)
}

// 本地未落库会话的排序兜底：把消息时间统一成可比较的 UTC ISO。
export function localConversationFallback(value) {
  const time = parseMessageTimestamp(value)
  return time ? new Date(time).toISOString() : null
}

export function compareConversationRecency(a = {}, b = {}) {
  if (!!a.is_running !== !!b.is_running) return a.is_running ? -1 : 1
  return conversationRecency(b) - conversationRecency(a)
}

export const CONVERSATION_LIST_LAYOUT = Object.freeze({
  FLAT: 'flat',
  GROUPED: 'grouped'
})

const SIDEBAR_LAYOUT_STORAGE_KEY = 'suyuan.sidebar.conversation-layout'

export function readSidebarConversationLayout() {
  try {
    return localStorage.getItem(SIDEBAR_LAYOUT_STORAGE_KEY) === CONVERSATION_LIST_LAYOUT.GROUPED
      ? CONVERSATION_LIST_LAYOUT.GROUPED
      : CONVERSATION_LIST_LAYOUT.FLAT
  } catch {
    return CONVERSATION_LIST_LAYOUT.FLAT
  }
}

export function writeSidebarConversationLayout(layout) {
  try {
    localStorage.setItem(
      SIDEBAR_LAYOUT_STORAGE_KEY,
      layout === CONVERSATION_LIST_LAYOUT.GROUPED
        ? CONVERSATION_LIST_LAYOUT.GROUPED
        : CONVERSATION_LIST_LAYOUT.FLAT
    )
  } catch {
    /* localStorage 不可用时静默降级为会话内状态 */
  }
}

export function resolveConversationAgentMode(session = {}) {
  const fromMetadata = String(session?.metadata?.mode || '').trim()
  if (fromMetadata) return fromMetadata
  const match = String(session?.session_id || '').match(/^([a-z_]+)_session_/)
  return match?.[1] || 'assistant'
}

export function groupSidebarConversationsByMode(sessions = [], knownModeIds = []) {
  const known = new Set(knownModeIds)
  const groups = new Map()
  for (const session of sessions) {
    const resolved = resolveConversationAgentMode(session)
    const mode = known.has(resolved) ? resolved : 'other'
    if (!groups.has(mode)) groups.set(mode, [])
    groups.get(mode).push(session)
  }
  // Map 保持插入序，即各组按组内最新会话时间排列（入参已排序）
  return Array.from(groups.entries()).map(([mode, items]) => ({ mode, sessions: items }))
}
