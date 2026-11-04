export function isAssistantFloatingRoute(route, authenticated, enabled) {
  return !!(enabled && authenticated && route && !route.meta?.public && !route.meta?.allowDashboardToken &&
    route.query?.embed !== '1')
}

export function floatingBadgeCount(conversations = []) {
  return conversations.reduce((total, row) => total + Math.max(0, Number(row.unread_count) || 0), 0)
}
