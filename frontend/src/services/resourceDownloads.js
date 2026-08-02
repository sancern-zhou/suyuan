import { authFetch } from '../auth/http.js'

const FORMAT_NAMES = {
  doc: 'DOC',
  docx: 'DOCX',
  html: 'HTML',
  md: 'Markdown',
  pdf: 'PDF',
  qmd: 'QMD',
  xls: 'Excel',
  xlsx: 'Excel'
}

export const formatName = resource => (
  FORMAT_NAMES[String(resource?.format || '').toLowerCase()]
  || String(resource?.format || '文件').toUpperCase()
)

export const downloadFileName = resource => {
  const label = String(resource?.label || 'download')
  const format = String(resource?.format || '').toLowerCase()
  if (!format || label.toLowerCase().endsWith(`.${format}`)) return label
  return `${label}.${format}`
}

const responseError = async response => {
  let detail = ''
  try {
    detail = String(await response.text()).trim()
  } catch {
    detail = ''
  }
  return detail || `下载失败（HTTP ${response.status}）`
}

export const downloadResource = async (resource, runtime = {}) => {
  if (!resource?.download_url) throw new Error('该资源不支持下载')
  const fetchImpl = runtime.fetchImpl || authFetch
  const documentRef = runtime.documentRef || globalThis.document
  const urlApi = runtime.urlApi || globalThis.URL
  const schedule = runtime.schedule || globalThis.setTimeout.bind(globalThis)
  const response = await fetchImpl(resource.download_url)
  if (!response.ok) throw new Error(await responseError(response))

  const objectUrl = urlApi.createObjectURL(await response.blob())
  let link = null
  let cleaned = false
  const cleanup = () => {
    if (cleaned) return
    cleaned = true
    try {
      link?.remove()
    } catch {
      // Revocation must still run when DOM cleanup fails.
    }
    try {
      urlApi.revokeObjectURL(objectUrl)
    } catch {
      // Cleanup failures must not turn a completed download into an error.
    }
  }
  try {
    link = documentRef.createElement('a')
    link.href = objectUrl
    link.download = downloadFileName(resource)
    documentRef.body.appendChild(link)
    link.click()
    try {
      schedule(cleanup, 0)
    } catch (error) {
      cleanup()
      throw error
    }
  } catch (error) {
    cleanup()
    throw error
  }
}

export const activeRendition = (group, format) => (
  (group?.resources || []).find(resource => (
    resource.status === 'active'
    && resource.relation === 'rendition'
    && resource.format === format
    && resource.download_url
  )) || null
)
