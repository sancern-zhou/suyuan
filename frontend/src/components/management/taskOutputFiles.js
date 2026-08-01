const OUTPUT_ROLES = new Set(['primary', 'output', 'report'])

const extensionFromName = (name = '') => {
  const lastDot = String(name).lastIndexOf('.')
  return lastDot > -1 ? String(name).slice(lastDot + 1).toUpperCase() : ''
}

export const executionStatusLabel = (status) => ({
  pending: '等待执行',
  running: '执行中',
  success: '执行成功',
  failed: '执行失败',
  timeout: '执行超时',
  cancelled: '已取消'
}[status] || '执行完成')

export function getTaskOutputFile(resource = {}) {
  if (!OUTPUT_ROLES.has(resource.role)) return null
  const url = resource.download_url || ''

  if (!url) return null

  const label = resource.label || '未命名文件'
  const format = resource.format || extensionFromName(label) || resource.kind || '文件'

  return {
    id: resource.resource_id || resource.ref_id || `${label}:${url}`,
    label,
    format: String(format).toUpperCase(),
    url,
    mimeType: resource.media_type || '',
    sizeBytes: Number(resource.size_bytes || 0),
    createdAt: resource.created_at || ''
  }
}

export function buildTaskOutputGroups(executions = [], resourcesBySession = {}) {
  return [...executions]
    .sort((left, right) => new Date(right.started_at || 0) - new Date(left.started_at || 0))
    .map((execution) => {
      const files = (resourcesBySession[execution.session_id] || [])
        .map(getTaskOutputFile)
        .filter(Boolean)
      return {
        executionId: execution.execution_id,
        sessionId: execution.session_id || '',
        status: execution.status || '',
        startedAt: execution.started_at || '',
        files
      }
    })
    .filter((group) => group.files.length > 0)
}

export function formatTaskOutputSize(sizeBytes) {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) return ''
  if (sizeBytes < 1024) return `${sizeBytes} B`
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}
