/**
 * 技能管理 API
 */
const API_BASE = '/api'

/**
 * 获取所有技能列表
 * @param {string} keyword - 可选，过滤关键词
 * @returns {Promise<Object>}
 */
export async function getSkillsList(keyword = null) {
  const params = keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''
  const response = await fetch(`${API_BASE}/skills${params}`)
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
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}`)
  if (!response.ok) {
    throw new Error(`获取技能详情失败: ${response.statusText}`)
  }
  return response.json()
}

/**
 * 刷新技能索引
 * @returns {Promise<Object>}
 */
export async function refreshSkillsIndex() {
  const response = await fetch(`${API_BASE}/skills/refresh-index`, {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error(`刷新技能索引失败: ${response.statusText}`)
  }
  return response.json()
}
