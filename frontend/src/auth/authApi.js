import { createCompanyCrypto, runtimeAuthConfig } from './companyCrypto.js'


async function responseBody(response) {
  const body = await response.json()
  if (!response.ok || body?.success === false) {
    throw new Error(body?.msg || body?.detail || 'Company authentication failed')
  }
  return body
}


export function createAuthApi({ fetchImpl = globalThis.fetch, storage, config } = {}) {
  const runtime = config || runtimeAuthConfig()
  const crypto = createCompanyCrypto(runtime)
  const url = path => `${runtime.authBaseUrl || ''}${path}`
  const session = () => storage?.readSession?.() || { token: '', sysCode: runtime.sysCode }

  return {
    async login({ username, password }) {
      const existing = session()
      const request = crypto.loginRequest(username, password, existing.token)
      return responseBody(await fetchImpl(url('/auth/token/authentication'), {
        method: 'POST',
        headers: { ...request.headers, SysCode: runtime.sysCode },
        body: JSON.stringify(request.body)
      }))
    },

    async currentUser(token) {
      const path = '/auth/account/getCurrentUser'
      return responseBody(await fetchImpl(`${url(path)}?isLog=1&logType=4`, {
        headers: {
          ...crypto.requestHeaders(path, token),
          Authorization: `Bearer ${token}`,
          SysCode: runtime.sysCode
        }
      }))
    },

    async logout(token) {
      const path = '/auth/token/logout'
      return responseBody(await fetchImpl(url(path), {
        method: 'POST',
        headers: {
          ...crypto.requestHeaders(path, token),
          Authorization: `Bearer ${token}`,
          SysCode: runtime.sysCode
        },
        body: JSON.stringify({ isLog: '1', logType: '6' })
      }))
    }
  }
}
