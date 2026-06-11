const getFileName = (filePath = '') => {
  if (!filePath || typeof filePath !== 'string') return ''
  const normalized = filePath.replace(/\\/g, '/')
  return normalized.split('/').pop() || normalized
}

const asArray = (value) => Array.isArray(value) ? value : []

const normalizeEntry = (entry) => {
  if (!entry || typeof entry !== 'object') return null

  const filePath = entry.file_path || entry.path || ''
  if (!filePath || typeof filePath !== 'string') return null

  const format = String(entry.format || entry.file_type || '').trim()
  const downloadLabel = entry.title || entry.downloadLabel || entry.file_name || getFileName(filePath) || '下载文件'
  const key = filePath

  return {
    format,
    file_path: filePath,
    downloadLabel,
    key
  }
}

export function normalizeRelatedArtifactFiles({ artifact = {}, refs = {} } = {}) {
  const candidates = [
    ...asArray(artifact.related_files),
    ...asArray(artifact.relatedFiles),
    ...asArray(artifact.artifacts),
    ...asArray(refs.artifacts)
  ]

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
