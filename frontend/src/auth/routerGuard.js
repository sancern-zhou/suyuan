export function safeRedirect(value, fallback = '/') {
  if (typeof value !== 'string') return fallback
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback
  }
  return value
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

    // 大屏直连：未登录但 URL 携带 access_token 时放行 dashboard 类页面，
    // 真实校验在后端（XUCHANG_DASHBOARD_ACCESS_TOKEN），无令牌的 API 请求会 401。
    if (!authStore.isAuthenticated && to.meta?.allowDashboardToken && to.query?.access_token) {
      return true
    }

    if (authStore.isAuthenticated) return true
    return {
      path: '/login',
      query: { redirect: safeRedirect(to.fullPath) }
    }
  }
}


export function installAuthGuard(router, authStore) {
  router.beforeEach(createAuthGuard(authStore))
}
