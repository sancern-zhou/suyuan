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
