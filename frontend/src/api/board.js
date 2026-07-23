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

export const restoreBoardVersion = async (boardId, versionId, baseRevision) => request(
  `/boards/${encodeURIComponent(boardId)}/restore`,
  {
    method: 'POST',
    body: JSON.stringify({ version_id: versionId, base_revision: baseRevision })
  }
)
