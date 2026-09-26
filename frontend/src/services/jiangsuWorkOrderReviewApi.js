import { authFetch } from '../auth/http'

const BASE = '/api/jiangsu/work-order-reviews'

function queryString(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

async function parse(response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail?.message || payload?.detail || '工单审核接口请求失败')
  return payload
}

export async function listWorkOrderReviews(params = {}) {
  return parse(await authFetch(`${BASE}${queryString(params)}`))
}

export async function getWorkOrderReview(code) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(code)}`))
}

export async function getWorkOrderReviewSource(code, name) {
  return parse(await authFetch(`${BASE}/${encodeURIComponent(code)}/sources/${encodeURIComponent(name)}`))
}

export async function fetchWorkOrderReviewAttachmentUrl(code, index) {
  const response = await authFetch(`${BASE}/${encodeURIComponent(code)}/attachments/${index}`)
  if (!response.ok) throw new Error('附件获取失败')
  return URL.createObjectURL(await response.blob())
}

// 人工操作（反馈/退回/归档）已从工作台移除，统一走任务调度中心审核卡片
// （/api/task-reviews/{id}/decision）；后端 operations 端点保留兼容旧入口。

