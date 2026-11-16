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

    // 部署级直连：未登录但 URL 携带 access_token 时放行标记了
    // allowDashboardToken 的页面，真实校验在后端
    // （dashboard_api_prefix + dashboard_access_token），
    // 无令牌的 API 请求会 401。
    if (!authStore.isAuthenticated && to.meta?.allowDashboardToken && to.query?.access_token) {
      return true
    }

    // 开发阶段页面（数据大屏/现场巡查快报）：仅超级管理员可见；
    // 墙屏令牌直连不受此限（后端令牌校验把关）。
    if (to.meta?.adminOnly && authStore.isAuthenticated) {
      const user = authStore.user
      const isAdmin =
        user?.isAdmin === true ||
        user?.admin === true ||
        (Array.isArray(user?.roleCodes) && user.roleCodes.includes('SUYUAN_ADMIN'))
      if (!isAdmin) return { path: '/' }
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
