import { authFetch } from '@/auth/http.js'

/**
 * 对话模式长期记忆 API
 *
 * 记忆按模式隔离存储于后端 DATA_REGISTRY/memory/{mode}/MEMORY.md，
 * 模式内所有用户共享；人工编辑采用乐观锁（版本号 + 文件 mtime）。
 */

const API_BASE_URL = ((import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/agent/memory`

async function responseErrorMessage(response, fallback) {
  try {
    const text = await response.text()
    if (!text) return fallback
    try {
      const data = JSON.parse(text)
      const detail = data?.detail
      if (typeof detail === 'string') return detail
      if (detail?.message) return detail.message
    } catch {
      return text
    }
    return fallback
  } catch {
    return fallback
  }
}

/**
 * 查看模式记忆
 * @returns {Promise<{mode: string, memory: string, meta: Object}>}
 */
export async function getModeMemory(mode) {
  const response = await authFetch(`${BASE_URL}/${encodeURIComponent(mode)}`)
  if (!response.ok) throw new Error('记忆读取失败')
  const data = await response.json()
  return {
    mode: String(data?.mode || mode),
    memory: String(data?.memory || ''),
    meta: (data?.meta && typeof data.meta === 'object') ? data.meta : {}
  }
}

/**
 * 保存模式记忆（乐观锁）
 * @returns {Promise<{mode: string, memory: string, meta: Object}>}
 */
export async function updateModeMemory(mode, content, expectedVersion, expectedMtimeNs = null) {
  const body = { content, expected_version: expectedVersion }
  if (expectedMtimeNs !== null && expectedMtimeNs !== undefined) {
    body.expected_mtime_ns = expectedMtimeNs
  }
  const response = await authFetch(`${BASE_URL}/${encodeURIComponent(mode)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!response.ok) {
    const error = new Error(await responseErrorMessage(response, '记忆保存失败'))
    error.status = response.status
    throw error
  }
  const data = await response.json()
  return {
    mode: String(data?.mode || mode),
    memory: String(data?.memory || ''),
    meta: (data?.meta && typeof data.meta === 'object') ? data.meta : {}
  }
}
