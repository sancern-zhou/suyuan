import { accountGeneration, assertAccountGeneration } from './accountSession.js'
import axios from 'axios'

import { browserAuthStorage } from './storage.js'


const ABSOLUTE_URL = /^[a-z][a-z\d+.-]*:\/\//i

// 公网防火墙会重置 PUT/PATCH/DELETE 连接（GET/POST 放行），网内统一改用
// POST + 方法覆盖头发送，由后端中间件还原真实方法后再路由。
const OVERRIDABLE_METHODS = ['PUT', 'DELETE', 'PATCH']


function configuredApiBase() {
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
  locationOrigin = globalThis.location?.origin
}) {
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
    const rawMethod = (fetchOptions.method ?? (typeof input === 'string' ? undefined : input?.method) ?? 'GET').toUpperCase()
    const response = await fetchImpl(url, applyMethodOverride(fetchOptions, headers, rawMethod, external))
    if (!external && !publicRequest && clearOnUnauthorized && response.status === 401) {
      // A delayed response from an earlier session must not log out a newer login.
      if (storage.readSession().token === requestToken) storage.clear()
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


function applyMethodOverride(fetchOptions, headers, rawMethod, external) {
  if (external || !OVERRIDABLE_METHODS.includes(rawMethod)) {
    return { ...fetchOptions, headers }
  }
  headers.set('X-HTTP-Method-Override', rawMethod)
  return { ...fetchOptions, method: 'POST', headers }
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
  const rawMethod = (config.method || 'get').toUpperCase()
  if (!external && OVERRIDABLE_METHODS.includes(rawMethod)) {
    config.method = 'post'
    config.headers['X-HTTP-Method-Override'] = rawMethod
  }
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
      if ((browserStorage().readSession().token || '') === error.config.accountToken) browserStorage().clear()
    }
    return Promise.reject(error)
  }
)
