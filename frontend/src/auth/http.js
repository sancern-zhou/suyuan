import { accountGeneration, assertAccountGeneration } from './accountSession.js'
import axios from 'axios'

import { browserAuthStorage } from './storage.js'


const ABSOLUTE_URL = /^[a-z][a-z\d+.-]*:\/\//i


// 运维平台登录态失效后，静默清会话只会让旧页面停在原地持续 401 轮询；
// company 认证下 401 即需要重新认证，统一送往登录页并携带回跳地址。
function redirectToLogin(location) {
  if (!location || location.pathname === '/login') return
  const target = `${location.pathname}${location.search}${location.hash}`
  location.assign(`/login?redirect=${encodeURIComponent(target)}`)
}


export function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


export function gatewayUrl(url, apiBaseUrl = configuredApiBase()) {
  if (
    url === apiBaseUrl ||
    url.startsWith(`${apiBaseUrl}/`) ||
    url.startsWith(`${apiBaseUrl}?`) ||
    url.startsWith(`${apiBaseUrl}#`)
  ) {
    return url
  }
  if (url === '/api') return apiBaseUrl
  if (url.startsWith('/api?') || url.startsWith('/api#')) return `${apiBaseUrl}${url.slice(4)}`
  if (url.startsWith('/api/')) return `${apiBaseUrl}${url.slice(4)}`
  return url
}


export function createAuthFetch({
  fetchImpl = globalThis.fetch,
  storage,
  apiBaseUrl = configuredApiBase(),
  locationOrigin = globalThis.location?.origin,
  loginLocation
}) {
  const locationForLogin = loginLocation
    ?? (globalThis.location && typeof globalThis.location.assign === 'function'
      ? globalThis.location
      : null)
  return async function authFetch(input, options = {}) {
    const {
      external = false,
      public: publicRequest = false,
      clearOnUnauthorized = true,
      ...fetchOptions
    } = options
    let rawUrl = typeof input === 'string' ? input : input.url
    if (input instanceof URL) {
      rawUrl = input.origin === locationOrigin
        ? `${input.pathname}${input.search}${input.hash}`
        : input.href
    }
    if (ABSOLUTE_URL.test(rawUrl) && !external) {
      throw new Error('Absolute URLs require external: true')
    }
    const url = external ? rawUrl : gatewayUrl(rawUrl, apiBaseUrl)
    const headers = new Headers(fetchOptions.headers || (typeof input === 'string' ? undefined : input.headers))
    const generation = accountGeneration()
    let requestToken = ''
    if (!external && !publicRequest) {
      const session = storage.readSession()
      requestToken = session.token || ''
      if (requestToken) headers.set('Authorization', `Bearer ${requestToken}`)
      headers.set('SysCode', session.sysCode || 'SUYUAN')
    } else {
      headers.delete('Authorization')
      headers.delete('SysCode')
    }
    const response = await fetchImpl(url, { ...fetchOptions, headers })
    if (!external && !publicRequest && clearOnUnauthorized && response.status === 401) {
      // A delayed response from an earlier session must not log out a newer login.
      if (storage.readSession().token === requestToken) {
        storage.clear()
        redirectToLogin(locationForLogin)
      }
    }
    if (!external && !publicRequest && response.status !== 401) {
      assertAccountGeneration(generation)
      // Parsing may finish after the account has changed as well.
      for (const method of ['json', 'text', 'blob', 'arrayBuffer']) {
        const read = response[method].bind(response)
        response[method] = async (...args) => {
          const value = await read(...args)
          assertAccountGeneration(generation)
          return value
        }
      }
    }
    return response
  }
}


function browserStorage() {
  return browserAuthStorage()
}


export const authFetch = (...args) => createAuthFetch({ storage: browserStorage() })(...args)


export const authAxios = axios.create()

authAxios.interceptors.request.use(config => {
  const external = config.external === true
  const publicRequest = config.public === true
  if (ABSOLUTE_URL.test(config.url || '') && !external) {
    throw new Error('Absolute URLs require external: true')
  }
  if (!external) config.url = gatewayUrl(config.url || '')
  if (!external && !publicRequest) {
    const session = browserStorage().readSession()
    config.headers.Authorization = session.token ? `Bearer ${session.token}` : undefined
    config.accountToken = session.token || ''
    config.accountGeneration = accountGeneration()
    config.headers.SysCode = session.sysCode || 'SUYUAN'
  } else {
    delete config.headers.Authorization
    delete config.headers.SysCode
  }
  config.accountProtected = !external && !publicRequest
  delete config.external
  delete config.public
  return config
})

authAxios.interceptors.response.use(
  response => {
    if (response.config.accountProtected) {
      assertAccountGeneration(response.config.accountGeneration)
    }
    return response
  },
  error => {
    if (error?.response?.status === 401 && error.config?.accountProtected) {
      const storage = browserStorage()
      if ((storage.readSession().token || '') === error.config.accountToken) {
        storage.clear()
        redirectToLogin(globalThis.location || null)
      }
    }
    return Promise.reject(error)
  }
)
