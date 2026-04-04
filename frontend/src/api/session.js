/**
 * 会话管理API模块
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/sessions`

/**
 * 通用请求方法
 */
async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }

  // 非 FormData 时设置 JSON Content-Type
  if (method !== 'GET' && method !== 'HEAD' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const config = {
    ...options,
    method,
    headers
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `HTTP error! status: ${response.status}`)
  }

  // 204 No Content
  if (response.status === 204) {
    return null
  }

  return await response.json()
}

/**
 * 获取会话列表
 */
export async function listSessions() {
  return await request(`${BASE_URL}/`)
}

/**
 * 获取会话详情
 */
export async function getSession(sessionId) {
  return await request(`${BASE_URL}/${sessionId}`)
}

/**
 * 获取会话统计
 */
export async function getSessionStats() {
  return await request(`${BASE_URL}/stats`)
}

/**
 * 恢复会话
 */
export async function restoreSession(sessionId) {
  return await request(`${BASE_URL}/${sessionId}/restore`, {
    method: 'POST'
  })
}

/**
 * 分页加载会话消息
 */
export async function getSessionMessages(sessionId, beforeSequence, limit = 30) {
  const params = new URLSearchParams()
  if (beforeSequence != null) params.set('before', beforeSequence)
  if (limit) params.set('limit', limit)
  return await request(`${BASE_URL}/${sessionId}/messages?${params}`)
}

/**
 * 归档会话
 */
export async function archiveSession(sessionId) {
  return await request(`${BASE_URL}/${sessionId}/archive`, {
    method: 'POST'
  })
}

/**
 * 导出会话
 */
export async function exportSession(sessionId) {
  return await request(`${BASE_URL}/${sessionId}/export`, {
    method: 'POST'
  })
}

/**
 * 删除会话
 */
export async function deleteSession(sessionId) {
  return await request(`${BASE_URL}/${sessionId}`, {
    method: 'DELETE'
  })
}

/**
 * 清理过期会话
 */
export async function cleanupSessions() {
  return await request(`${BASE_URL}/cleanup`, {
    method: 'POST'
  })
}
