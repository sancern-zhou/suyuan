export function safeRedirect(value, fallback = '/') {
  if (typeof value !== 'string') return fallback
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback
  }
  return value
}


export function createAuthGuard(authStore, { onOperationLoginRequired = null } = {}) {
  return async to => {
    if (to.path === '/access-denied') return true
    if (!authStore.initialized) {
      try {
        await authStore.bootstrap()
      } catch {
        // The store clears an invalid persisted session before returning here.
      }
    }

    // Accounts denied by the unit whitelist must land on the notice page
    // instead of bouncing back to the ops-platform login forever.
    if (authStore.accessDenied) {
      return { path: '/access-denied' }
    }

    if (to.path === '/login') {
      if (authStore.isAuthenticated) return safeRedirect(to.query?.redirect)
      if (authStore.authMode === 'operation' && onOperationLoginRequired) {
        onOperationLoginRequired()
        return false
      }
      return true
    }

    // 部署级直连：未登录但 URL 携带 access_token 时放行标记了
    // allowDashboardToken 的页面，真实校验在后端
    // （dashboard_api_prefix + dashboard_access_token），
    // 无令牌的 API 请求会 401。
    if (!authStore.isAuthenticated && to.meta?.allowDashboardToken && to.query?.access_token) {
      return true
    }

    if (authStore.isAuthenticated) return true
    if (authStore.authMode === 'operation' && onOperationLoginRequired) {
      onOperationLoginRequired()
      return false
    }
    return {
      path: '/login',
      query: { redirect: safeRedirect(to.fullPath) }
    }
  }
}


export function installAuthGuard(router, authStore, options = {}) {
  router.beforeEach(createAuthGuard(authStore, options))
}
