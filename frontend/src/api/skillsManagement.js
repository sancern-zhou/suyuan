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
 * 获取待审核技能草稿列表
 * @returns {Promise<Object>}
 */
export async function getSkillDraftsList() {
  const response = await fetch(`${API_BASE}/skills/drafts`)
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
  const response = await fetch(`${API_BASE}/skills/drafts/${encodeURIComponent(draftName)}`)
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
  const response = await fetch(`${API_BASE}/skills/refresh-index`, {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error(`刷新技能索引失败: ${response.statusText}`)
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
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}`, {
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
  const response = await fetch(`${API_BASE}/skills/drafts/${encodeURIComponent(draftName)}`, {
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
