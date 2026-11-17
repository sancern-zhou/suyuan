function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


function nonEmptyString(value) {
  return typeof value === 'string' && Boolean(value.trim())
}


export function normalizeSsoExchange(value, sysCode) {
  if (!value || typeof value !== 'object') throw new Error('外部登录校验失败')
  const token = nonEmptyString(value.token) ? value.token.trim() : ''
  const user = value.user
  if (!token) throw new Error('外部登录未返回会话令牌')
  if (!user || !nonEmptyString(user.id) || !nonEmptyString(user.userName)) {
    throw new Error('外部登录未返回用户信息')
  }
  return {
    token,
    sysCode: nonEmptyString(value.sysCode) ? value.sysCode.trim() : sysCode,
    user: {
      ...user,
      name: nonEmptyString(user.name) ? user.name : user.userName,
      roleCodes: Array.isArray(user.roleCodes) ? user.roleCodes : []
    }
  }
}


export async function exchangeSsoTicket({
  ticket,
  fetchImpl = globalThis.fetch,
  apiBaseUrl = configuredApiBase(),
  timeoutMs = 8000
} = {}) {
  if (!nonEmptyString(ticket)) throw new Error('缺少外部登录票据')
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const base = apiBaseUrl.replace(/\/$/, '')
    const response = await fetchImpl(`${base}/auth/sso/exchange`, {
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket: ticket.trim() }),
      signal: controller.signal
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(body?.detail || '外部登录校验失败')
    }
    return body
  } finally {
    clearTimeout(timeoutId)
  }
}
