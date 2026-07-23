import { gatewayUrl } from '../auth/http.js'

const getFileName = (filePath = '') => {
  if (!filePath || typeof filePath !== 'string') return ''
  const normalized = filePath.replace(/\\/g, '/')
  return normalized.split('/').pop() || normalized
}

const asArray = (value) => Array.isArray(value) ? value : []
const DOWNLOADABLE_FORMATS = new Set(['drawio', 'drawio_svg', 'svg', 'png'])

const normalizeFormat = (value = '') => {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s.-]+/g, '_')
}

export const normalizeArtifactUrl = (url = '', options = {}) => {
  if (!url || typeof url !== 'string') return url
  const { apiBaseUrl, origin } = options

  if (
    url === '/api' ||
    url.startsWith('/api/') ||
    url.startsWith('/api?') ||
    url.startsWith('/api#')
  ) {
    return gatewayUrl(url, apiBaseUrl)
  }

  const browserOrigin = origin || globalThis.location?.origin || ''
  if (!browserOrigin) return url

  try {
    const normalizedOrigin = new URL(browserOrigin).origin
    const parsed = new URL(url, normalizedOrigin)
    if (
      parsed.origin === normalizedOrigin &&
      (parsed.pathname === '/api' || parsed.pathname.startsWith('/api/'))
    ) {
      return gatewayUrl(
        `${parsed.pathname}${parsed.search}${parsed.hash}`,
        apiBaseUrl
      )
    }
  } catch (error) {
    return url
  }

  return url
}

const hasStandaloneFileSignal = (artifact = {}) => {
  return Boolean(
    artifact.format ||
    artifact.file_type ||
    artifact.file_name ||
    artifact.title ||
    artifact.downloadLabel
  )
}

const getRelatedFileCandidates = ({ artifact = {}, refs = {} } = {}) => {
  const candidates = [
    ...asArray(artifact.related_files),
    ...asArray(artifact.relatedFiles),
    ...asArray(artifact.artifacts),
    ...asArray(refs.artifacts)
  ]

  if ((artifact.file_path || artifact.path) && hasStandaloneFileSignal(artifact)) {
    candidates.push(artifact)
  }

  return candidates
}

export function buildArtifactDownloadPayload({ result = {}, latestVisualization = {}, content = {} } = {}) {
  const data = result?.data || {}
  const primaryArtifact = data.artifact || result?.artifact || {}
  const refs = data.refs || result?.refs || content?.refs || latestVisualization?.refs || {}

  return {
    ...primaryArtifact,
    ...latestVisualization,
    ...result,
    ...data,
    related_files: [
      ...asArray(data.related_files),
      ...asArray(result?.related_files),
      ...asArray(primaryArtifact.related_files),
      ...asArray(latestVisualization?.related_files),
      ...asArray(content?.related_files)
    ],
    relatedFiles: [
      ...asArray(data.relatedFiles),
      ...asArray(result?.relatedFiles),
      ...asArray(primaryArtifact.relatedFiles),
      ...asArray(latestVisualization?.relatedFiles),
      ...asArray(content?.relatedFiles)
    ],
    artifacts: [
      ...asArray(data.artifacts),
      ...asArray(result?.artifacts),
      ...asArray(primaryArtifact.artifacts),
      ...asArray(latestVisualization?.artifacts),
      ...asArray(content?.artifacts)
    ],
    refs
  }
}

const normalizeEntry = (entry) => {
  if (!entry || typeof entry !== 'object') return null

  const filePath = entry.file_path || entry.path || ''
  if (!filePath || typeof filePath !== 'string') return null

  const format = normalizeFormat(entry.format || entry.file_type || '')
  if (format && !DOWNLOADABLE_FORMATS.has(format)) return null

  const downloadLabel = entry.title || entry.downloadLabel || entry.file_name || getFileName(filePath) || '下载文件'
  const key = filePath
  const rawUrl = entry.url || `/api/file/${encodeURIComponent(filePath)}`

  return {
    format,
    file_path: filePath,
    url: normalizeArtifactUrl(rawUrl),
    relative_path: entry.relative_path,
    downloadLabel,
    key
  }
}

export function normalizeRelatedArtifactFiles({ artifact = {}, refs = {} } = {}) {
  const candidates = getRelatedFileCandidates({ artifact, refs })

  const seen = new Set()
  const files = []

  candidates.forEach(entry => {
    const normalized = normalizeEntry(entry)
    if (!normalized || seen.has(normalized.key)) return

    seen.add(normalized.key)
    files.push(normalized)
  })

  return files
}

export function hasRelatedArtifactFiles({ artifact = {}, refs = {} } = {}) {
  return normalizeRelatedArtifactFiles({ artifact, refs }).length > 0
}
