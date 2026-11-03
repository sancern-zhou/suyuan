// 统一鉴权平台 OAuth2.0 授权码交换（见《基于OAuth2.0协议接入平台页面》v1.2）。
// client_secret 只在后端 /auth/oauth/exchange 参与，浏览器侧仅传一次性 code。
import { configuredApiBase } from './http.js'


async function responseBody(response) {
  const body = await response.json().catch(() => null)
  if (!response.ok || !body || body.success === false) {
    throw new Error(body?.detail || body?.message || 'OAuth 授权码交换失败')
  }
  return body
}


export function createOAuthApi({ fetchImpl = globalThis.fetch, apiBaseUrl = configuredApiBase() } = {}) {
  const base = String(apiBaseUrl || '/api/suyuan').replace(/\/$/, '')
  return {
    async exchangeCode(code, redirectUri) {
      const params = new URLSearchParams({ code, redirectUri })
      const body = await responseBody(
        await fetchImpl(`${base}/auth/oauth/exchange?${params.toString()}`)
      )
      const accessToken = String(body.accessToken || '').trim()
      if (!accessToken) throw new Error('OAuth 授权码交换未返回访问令牌')
      return {
        accessToken,
        refreshToken: String(body.refreshToken || ''),
        expiresIn: Number(body.expiresIn) || 0
      }
    }
  }
}


// 会话身份查询：走本方后端网关（服务端完成平台应用编码回退），
// 浏览器不直接调用统一鉴权平台的 getCurrentUser。
export function createSessionApi({
  fetchImpl = globalThis.fetch,
  apiBaseUrl = configuredApiBase(),
  sysCode = 'SUYUAN'
} = {}) {
  const base = String(apiBaseUrl || '/api/suyuan').replace(/\/$/, '')
  return {
    async me(token) {
      const response = await fetchImpl(`${base}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
          SysCode: sysCode
        }
      })
      return { result: await responseBody(response) }
    }
  }
}
