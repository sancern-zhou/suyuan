import { authFetch } from '../auth/http.js'

async function request(path, options) {
  const response = await authFetch(`/api/task-reviews${path}`, options)
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '审核请求失败')
  return payload
}
export const listTaskReviews = (offset = 0) => request(`?pending_only=true&limit=1000&offset=${offset}`)
export const getTaskReview = id => request(`/${encodeURIComponent(id)}`)
export const decideTaskReview = (id, decision) => request(`/${encodeURIComponent(id)}/decision`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(decision)
})
export async function fetchReviewEvidenceUrl(id, index) {
  const response = await authFetch(`/api/task-reviews/${encodeURIComponent(id)}/evidence/${index}`)
  if (!response.ok) throw new Error('证据文件读取失败')
  return URL.createObjectURL(await response.blob())
}
export async function downloadReviewEvidence(id, index) {
  const response = await authFetch(`/api/task-reviews/${encodeURIComponent(id)}/evidence/${index}`)
  if (!response.ok) throw new Error('证据文件读取失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = decodeURIComponent(response.headers.get('content-disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1] || `evidence-${index}`)
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
