export function isAssistantFloatingRoute(route, authenticated, enabled) {
  return !!(enabled && authenticated && route && !route.meta?.public && !route.meta?.allowDashboardToken &&
    route.query?.embed !== '1')
}

export function floatingBadgeCount(conversations = []) {
  return conversations.reduce((total, row) => total + Math.max(0, Number(row.unread_count) || 0), 0)
}

// 角标统计全部会话的未读，而已读上报只作用于当前会话；点开浮窗时若
// 未读落在别的会话，需要定位到应聚焦的会话（列表按 last_message_at 倒序，
// 取最近更新的未读会话）。当前会话已带未读时返回 null 保持不动。
export function nextUnreadFocus(conversations = [], currentSessionId = null) {
  const rows = (conversations || []).filter(row => (Number(row.unread_count) || 0) > 0 && row.session_id)
  if (!rows.length) return null
  if (currentSessionId && rows.some(row => row.session_id === currentSessionId)) return null
  return rows[0]
}
