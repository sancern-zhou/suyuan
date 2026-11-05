const ROUTE_TITLES = {
  analysis: '智能体平台',
  session: '会话工作区',
  fetchers: '数据抓取管理',
  'knowledge-base': '知识库管理',
  'tools-management': '工具管理',
  'skills-management': '技能管理',
  'social-accounts': '社交账号管理',
  'expert-deliberation': '专家会商推演'
}

export function buildAssistantPageContext(route) {
  if (!route || route.meta?.public || route.meta?.allowDashboardToken) return null
  const name = typeof route.name === 'string' ? route.name : ''
  if (!name || !ROUTE_TITLES[name]) return null
  const context = { route_name: name, title: route.meta?.title || ROUTE_TITLES[name] }
  // 只带导航事实，不复制 URL、DOM 或筛选条件，避免泄露凭证与不可信页面文本。
  if (name === 'session' && typeof route.params?.id === 'string') context.session_id = route.params.id.slice(0, 160)
  return context
}
