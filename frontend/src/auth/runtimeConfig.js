function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


export function companyRuntimeConfig() {
  return { authMode: 'company', sysCode: 'SUYUAN', mockUser: null }
}


export function normalizeAuthRuntimeConfig(value) {
  if (!value || typeof value !== 'object') return companyRuntimeConfig()
  const sysCode = typeof value.sysCode === 'string' && value.sysCode
    ? value.sysCode
    : 'SUYUAN'
  if (value.authMode === 'company') {
    return { authMode: 'company', sysCode, mockUser: null }
  }
  const user = value.mockUser
  if (
    value.authMode !== 'mock' ||
    !user ||
    typeof user.id !== 'string' ||
    !user.id ||
    user.isAdmin !== true
  ) {
    return companyRuntimeConfig()
  }
  return { authMode: 'mock', sysCode, mockUser: { ...user } }
}


export async function loadAuthRuntimeConfig({
  fetchImpl = globalThis.fetch,
  apiBaseUrl = configuredApiBase()
} = {}) {
  try {
    const base = apiBaseUrl.replace(/\/$/, '')
    const response = await fetchImpl(`${base}/auth/runtime-config`, {
      cache: 'no-store',
      credentials: 'same-origin'
    })
    if (!response.ok) return companyRuntimeConfig()
    return normalizeAuthRuntimeConfig(await response.json())
  } catch {
    return companyRuntimeConfig()
  }
}


export async function initializeAuthStore(authStore, { load = loadAuthRuntimeConfig } = {}) {
  const config = await load()
  authStore.configure(config)
  return config
}
