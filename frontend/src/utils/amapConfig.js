const DEFAULT_API_BASE = '/api'

export async function resolveAMapConfig({ env = {}, fetchImpl = globalThis.fetch } = {}) {
  const envKey = env?.VITE_AMAP_KEY
  if (envKey) {
    return {
      key: envKey,
      securityJsCode: env?.VITE_AMAP_SECURITY_CODE || ''
    }
  }

  if (typeof fetchImpl !== 'function') {
    return { key: '', securityJsCode: '' }
  }

  // 子路径部署（如 /suyuan/）时 VITE_API_BASE_URL=/suyuan/api/suyuan，
  // 配置接口须按同一路径前缀请求，否则会落到其他应用。
  const base = String(env?.VITE_API_BASE_URL || DEFAULT_API_BASE).replace(/\/+$/, '')
  try {
    const response = await fetchImpl(`${base}/config`)
    if (!response?.ok) {
      return { key: '', securityJsCode: '' }
    }
    const config = await response.json()
    return {
      key: config?.amapPublicKey || '',
      securityJsCode: config?.amapSecurityCode || ''
    }
  } catch {
    return { key: '', securityJsCode: '' }
  }
}
