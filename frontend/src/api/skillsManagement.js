import { authFetch } from '@/auth/http.js'
/**
 * 技能管理 API
 */
// Keep skill-management calls on the active project's API gateway.  A bare
// `/api` escapes the standalone project prefix (`/api/suyuan`) and can route
// an isolated frontend to the default backend instead.
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * 获取所有技能列表
 * @param {string} keyword - 可选，过滤关键词
 * @returns {Promise<Object>}
 */
export async function getSkillsList(keyword = null, mode = null) {
  const search = new URLSearchParams()
  if (keyword) search.set('keyword', keyword)
  if (mode) search.set('mode', mode)
  const params = search.toString() ? `?${search}` : ''
  const response = await authFetch(`${API_BASE}/skills${params}`)
  if (!response.ok) {
    throw new Error(`获取技能列表失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 获取单个技能详情
 * @param {string} skillName - 技能文件名（如 "excel.md" 或 "excel"）
 * @returns {Promise<Object>}
 */
export async function getSkillDetail(skillName) {
  const response = await authFetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}`)
  if (!response.ok) {
    throw new Error(`获取技能详情失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 获取待审核技能草稿列表
 * @returns {Promise<Object>}
 */
export async function getSkillDraftsList() {
  const response = await authFetch(`${API_BASE}/skills/drafts`)
  if (!response.ok) {
    throw new Error(`获取待审核技能列表失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 获取单个待审核技能草稿详情
 * @param {string} draftName - 草稿文件名（如 "draft.md" 或 "draft"）
 * @returns {Promise<Object>}
 */
export async function getSkillDraftDetail(draftName) {
  const response = await authFetch(`${API_BASE}/skills/drafts/${encodeURIComponent(draftName)}`)
  if (!response.ok) {
    throw new Error(`获取待审核技能详情失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 刷新技能索引
 * @returns {Promise<Object>}
 */
export async function refreshSkillsIndex() {
  const response = await authFetch(`${API_BASE}/skills/refresh-index`, {
    method: 'POST'
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || data.message || response.statusText || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 保存技能文档
 * @param {string} skillName - 技能文件名（如 "excel.md" 或 "excel"）
 * @param {string} content - 新的文档内容
 * @returns {Promise<Object>}
 */
export async function saveSkillDetail(skillName, content) {
  const response = await authFetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ content })
  })
  if (!response.ok) {
    throw new Error(`保存技能文档失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 保存待审核技能草稿
 * @param {string} draftName - 草稿文件名（如 "draft.md" 或 "draft"）
 * @param {string} content - 新的文档内容
 * @returns {Promise<Object>}
 */
export async function saveSkillDraftDetail(draftName, content) {
  const response = await authFetch(`${API_BASE}/skills/drafts/${encodeURIComponent(draftName)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ content })
  })
  if (!response.ok) {
    throw new Error(`保存待审核技能草稿失败: ${response.statusText}`)
  }
  return response.json()
}
