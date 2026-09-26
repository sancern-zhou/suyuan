import { authFetch } from '@/auth/http.js'
/**
 * 常用问题（coordinator quick prompts）API
 * 读接口所有登录用户可用；admin 接口需要管理员角色（后端 enforce）。
 */
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

/**
 * 获取当前项目启用中的常用问题（coordinator 首页展示列表）
 * @returns {Promise<{items: Array<{id:number,label:string,prompt:string,mode:string|null}>}>}
 */
export async function getCoordinatorQuickPrompts() {
  const response = await authFetch(`${API_BASE}/project/coordinator/quick-prompts`)
  if (!response.ok) {
    throw new Error(`获取常用问题失败: HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 获取输入框上方按智能体模式显示的常用问题（surface=input）
 * @returns {Promise<{items: Array<{id:number,label:string,prompt:string,mode:string}>}>}
 */
export async function getInputQuickPrompts() {
  const response = await authFetch(`${API_BASE}/project/coordinator/quick-prompts?surface=input`)
  if (!response.ok) {
    throw new Error(`获取输入框常用问题失败: HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 管理端列表（含停用项）+ 可选智能体模式
 * @returns {Promise<{items: Array<Object>, modes: Array<{id:string,name:string,shortName:string}>}>}
 */
export async function adminListQuickPrompts() {
  const response = await authFetch(`${API_BASE}/admin/coordinator/quick-prompts`)
  if (!response.ok) {
    throw new Error(`获取常用问题列表失败: HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 新增常用问题
 * @param {{label:string, prompt:string, mode:string|null}} payload
 */
export async function adminCreateQuickPrompt(payload) {
  const response = await authFetch(`${API_BASE}/admin/coordinator/quick-prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return consumeMutation(response, '新增常用问题失败')
}

/**
 * 更新常用问题（label / prompt / mode / enabled 任意子集）
 * @param {number} id
 * @param {Partial<{label:string, prompt:string, mode:string|null, enabled:boolean}>} payload
 */
export async function adminUpdateQuickPrompt(id, payload) {
  const response = await authFetch(`${API_BASE}/admin/coordinator/quick-prompts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return consumeMutation(response, '更新常用问题失败')
}

/**
 * 删除常用问题
 * @param {number} id
 */
export async function adminDeleteQuickPrompt(id) {
  const response = await authFetch(`${API_BASE}/admin/coordinator/quick-prompts/${id}`, {
    method: 'DELETE'
  })
  return consumeMutation(response, '删除常用问题失败')
}

/**
 * 按给定 id 顺序重新排序（首页为整表排序；输入框按 mode 范围排序）
 * @param {number[]} orderedIds
 * @param {{surface?: 'home'|'input', mode?: string|null}} [scope]
 */
export async function adminReorderQuickPrompts(orderedIds, scope = {}) {
  const response = await authFetch(`${API_BASE}/admin/coordinator/quick-prompts/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      orderedIds,
      surface: scope.surface || 'home',
      mode: scope.mode ?? null
    })
  })
  return consumeMutation(response, '排序保存失败')
}

async function consumeMutation(response, fallbackMessage) {
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || fallbackMessage)
  }
  return response.json()
}
