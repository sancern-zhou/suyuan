import axios from 'axios'

import { browserAuthStorage } from './storage.js'


const ABSOLUTE_URL = /^[a-z][a-z\d+.-]*:\/\//i


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
      if (storage.readSession().token === requestToken) storage.clear()
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
    config.headers.SysCode = session.sysCode || 'SUYUAN'
  } else {
    delete config.headers.Authorization
    delete config.headers.SysCode
  }
  delete config.external
  delete config.public
  return config
})

authAxios.interceptors.response.use(
  response => response,
  error => {
    if (error?.response?.status === 401 && !error.config?.external && !error.config?.public) {
      browserStorage().clear()
    }
    return Promise.reject(error)
  }
)
