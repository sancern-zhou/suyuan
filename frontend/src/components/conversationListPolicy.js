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
