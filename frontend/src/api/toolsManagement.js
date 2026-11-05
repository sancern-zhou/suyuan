import { authFetch } from '@/auth/http.js'
/**
 * 工具/技能管理 API
 */
// Keep tool-management calls on the active project's API gateway.  A bare
// `/api` escapes the standalone project prefix (`/api/suyuan`) and can route
// an isolated frontend to the default backend instead.
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * 获取所有工具列表
 * @returns {Promise<Object>}
 */
export async function getToolsList() {
  const response = await authFetch(`${API_BASE}/tools`)
  if (!response.ok) {
    throw new Error(`获取工具列表失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 获取单个工具详情
 * @param {string} toolName - 工具名称
 * @returns {Promise<Object>}
 */
export async function getToolDetail(toolName) {
  const response = await authFetch(`${API_BASE}/tools/${encodeURIComponent(toolName)}`)
  if (!response.ok) {
    throw new Error(`获取工具详情失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 更新工具状态
 * @param {string} toolName - 工具名称
 * @param {boolean} enabled - 是否启用
 * @returns {Promise<Object>}
 */
export async function updateToolStatus(toolName, enabled) {
  const response = await authFetch(`${API_BASE}/tools/${encodeURIComponent(toolName)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ enabled })
  })
  if (!response.ok) {
    throw new Error(`更新工具状态失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 获取所有工具类别
 * @returns {Promise<Object>}
 */
export async function getToolsCategories() {
  const response = await authFetch(`${API_BASE}/tools/categories`)
  if (!response.ok) {
    throw new Error(`获取工具类别失败: ${response.statusText}`)
  }
  return response.json()
}
