import { ENTRY_OAUTH_KEYS, ENTRY_TOKEN_KEYS } from './entryToken.js'


export function safeRedirect(value, fallback = '/') {
  if (typeof value !== 'string') return fallback
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback
  }
  return value
}


// 入口 token / OAuth 授权码只服务于首次握手；跳转登录页等重定向目标里不携带，
// 避免失效凭证残留在地址栏与跳转链中。
export function fullPathWithoutEntryToken(to) {
  const query = { ...(to?.query || {}) }
  const sensitiveKeys = [...ENTRY_TOKEN_KEYS, ...ENTRY_OAUTH_KEYS]
  const hasEntryCredential = sensitiveKeys.some(key => key in query)
  if (!hasEntryCredential) return to?.fullPath || to?.path || '/'
  for (const key of sensitiveKeys) delete query[key]
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) continue
    for (const item of Array.isArray(value) ? value : [value]) {
      search.append(key, String(item))
    }
  }
  const queryString = search.toString()
  return `${to?.path || '/'}${queryString ? `?${queryString}` : ''}`
}


export function createAuthGuard(authStore) {
  return async to => {
    if (!authStore.initialized) {
      try {
        await authStore.bootstrap()
      } catch {
        // The store clears an invalid persisted session before returning here.
      }
    }

    if (to.path === '/login') {
      return authStore.isAuthenticated
        ? safeRedirect(to.query?.redirect)
        : true
    }

    // 部署级直连：未登录但 URL 携带 access_token 时放行标记了
    // allowDashboardToken 的页面，真实校验在后端
    // （dashboard_api_prefix + dashboard_access_token），
    // 无令牌的 API 请求会 401。
    if (!authStore.isAuthenticated && to.meta?.allowDashboardToken && to.query?.access_token) {
      return true
    }

    if (authStore.isAuthenticated) return true
    return {
      path: '/login',
      query: { redirect: safeRedirect(fullPathWithoutEntryToken(to)) }
    }
  }
}


export function installAuthGuard(router, authStore) {
  router.beforeEach(createAuthGuard(authStore))
}
