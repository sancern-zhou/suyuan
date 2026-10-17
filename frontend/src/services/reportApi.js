import { authFetch } from '@/auth/http.js'
import { readReportResponse } from './reportStream.js'

const API_BASE = '/api/report'

/** Generate a report using template text through the current Agent. */
export async function generateFromTemplateAgent(params) {
  const response = await authFetch(`${API_BASE}/generate-from-template-agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  })
  const { reportContent } = await readReportResponse(response)
  return reportContent
}

/** Generate from an uploaded template and retain its conversation identity. */
export async function generateFromTemplateFile(file, params) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('start', params.start)
  formData.append('end', params.end)
  if (params.display) formData.append('display', params.display)

  const response = await authFetch(`${API_BASE}/generate-from-template-file`, {
    method: 'POST',
    body: formData
  })
  return readReportResponse(response)
}

/** Saved and uploaded templates share the same response contract. */
export async function generateFromSavedTemplate(templateId, params) {
  const response = await authFetch(`${API_BASE}/templates/${encodeURIComponent(templateId)}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  })
  return readReportResponse(response)
}

/**
 * 获取模板列表
 * @returns {Promise<Array>} 模板列表
 */
export async function listTemplates() {
  const response = await authFetch(`${API_BASE}/templates`)

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 创建模板
 * @param {Object} params - 模板参数
 * @returns {Promise<Object>} 创建的模板
 */
export async function createTemplate(params) {
  const formData = new FormData()
  formData.append('name', params.name)
  formData.append('source_report', params.source_report)
  if (params.description) {
    formData.append('description', params.description)
  }

  const response = await authFetch(`${API_BASE}/templates`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 上传模板文件
 * @param {File} file - 模板文件
 * @param {Object} metadata - 元数据
 * @returns {Promise<Object>} 上传结果
 */
export async function uploadTemplate(file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)

  if (metadata.name) {
    formData.append('name', metadata.name)
  }
  if (metadata.description) {
    formData.append('description', metadata.description)
  }

  const response = await authFetch(`${API_BASE}/upload-template`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}
