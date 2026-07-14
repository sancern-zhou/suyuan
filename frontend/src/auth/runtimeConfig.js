function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


export function companyRuntimeConfig() {
  return { authMode: 'company', sysCode: 'SUYUAN', mockUser: null }
}


function nonEmptyString(value) {
  return typeof value === 'string' && Boolean(value.trim())
}


export function normalizeAuthRuntimeConfig(value) {
  if (!value || typeof value !== 'object') return companyRuntimeConfig()
  if (!nonEmptyString(value.sysCode)) return companyRuntimeConfig()
  const sysCode = value.sysCode.trim()
  if (value.authMode === 'company') {
    return { authMode: 'company', sysCode, mockUser: null }
  }
  const user = value.mockUser
  if (
    value.authMode !== 'mock' ||
    !user ||
    !nonEmptyString(user.id) ||
    !nonEmptyString(user.userName) ||
    !nonEmptyString(user.name) ||
    !Array.isArray(user.roleCodes) ||
    !user.roleCodes.every(nonEmptyString) ||
    !user.roleCodes.includes('SUYUAN_ADMIN') ||
    user.isAdmin !== true ||
    user.authSource !== 'mock' ||
    user.sysCode !== sysCode
  ) {
    return companyRuntimeConfig()
  }
  return {
    authMode: 'mock',
    sysCode,
    mockUser: { ...user, roleCodes: [...user.roleCodes] }
  }
}


export async function loadAuthRuntimeConfig({
  fetchImpl = globalThis.fetch,
  apiBaseUrl = configuredApiBase(),
  timeoutMs = 5000
} = {}) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const base = apiBaseUrl.replace(/\/$/, '')
    const response = await fetchImpl(`${base}/auth/runtime-config`, {
      cache: 'no-store',
      credentials: 'same-origin',
      signal: controller.signal
    })
    if (!response.ok) return companyRuntimeConfig()
    return normalizeAuthRuntimeConfig(await response.json())
  } catch {
    return companyRuntimeConfig()
  } finally {
    clearTimeout(timeoutId)
  }
}


export async function initializeAuthStore(authStore, { load = loadAuthRuntimeConfig } = {}) {
  const config = await load()
  authStore.configure(config)
  return config
}
