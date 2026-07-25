import { authFetch } from '@/auth/http.js'


const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const request = async (path, options = {}) => {
  const response = await authFetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload?.detail
    const error = new Error(detail?.code || detail || `board_request_failed_${response.status}`)
    error.code = detail?.code || detail || 'board_request_failed'
    error.status = response.status
    error.details = detail
    throw error
  }
  return payload
}

export const commitManualBoardVersion = async (boardId, payload) => request(
  `/boards/${encodeURIComponent(boardId)}/versions/manual`,
  { method: 'POST', body: JSON.stringify(payload) }
)

export const saveBoardDraft = async (boardId, xml) => request(
  `/boards/${encodeURIComponent(boardId)}/draft`,
  { method: 'PUT', body: JSON.stringify({ xml }) }
)

export const getBoardVersions = async (boardId) => request(
  `/boards/${encodeURIComponent(boardId)}/versions`
)

export const getBoardVersion = async (boardId, versionId) => request(
  `/boards/${encodeURIComponent(boardId)}/versions/${encodeURIComponent(versionId)}`
)

const readBoardVersionXmlRef = async (xmlRef = {}) => {
  const directUrl = xmlRef.read_url || xmlRef.url || xmlRef.download_url
  const localPath = xmlRef.local_path || xmlRef.path || xmlRef.file_path
  const normalizedDirectUrl = directUrl?.startsWith('/api/') && API_BASE_URL !== '/api'
    ? `${API_BASE_URL}${directUrl.slice(4)}`
    : directUrl
  const url = normalizedDirectUrl || (localPath ? `${API_BASE_URL}/file/${encodeURIComponent(localPath)}` : '')
  if (!url) throw new Error('board_version_xml_ref_missing')

  const response = await authFetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`board_version_xml_load_failed_${response.status}`)
  }
  return await response.text()
}

export const loadBoardVersionXml = async (boardId, versionId, version = {}) => {
  const inlineXml = version.xml || version.current_xml || ''
  let versionPayload = version
  if (!inlineXml && !versionPayload.xml_ref) {
    if (!boardId || !versionId) throw new Error('board_version_identity_missing')
    const response = await getBoardVersion(boardId, versionId)
    versionPayload = response.version || response
  }

  const xml = inlineXml || versionPayload.xml || versionPayload.current_xml || await readBoardVersionXmlRef(versionPayload.xml_ref)
  const trimmed = String(xml || '').trim()
  if (!trimmed.startsWith('<mxfile') && !trimmed.startsWith('<mxGraphModel')) {
    throw new Error('board_version_xml_invalid')
  }
  return xml
}
