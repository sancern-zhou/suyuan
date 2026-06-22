const API_CONFIG_URL = '/api/config'

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

  try {
    const response = await fetchImpl(API_CONFIG_URL)
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
