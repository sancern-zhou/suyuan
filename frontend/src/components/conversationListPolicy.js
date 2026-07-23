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
