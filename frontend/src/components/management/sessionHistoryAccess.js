const SOURCE_LABELS = Object.freeze({
  web: 'Web',
  knowledge_qa: '知识库',
  social: '微信'
})

const CATALOG_FIELDS = Object.freeze([
  'source',
  'owner_user_id',
  'owner_username',
  'owner_display_name',
  'read_only_on_web'
])

export function preserveCatalogFields(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming }
  for (const key of CATALOG_FIELDS) {
    if (incoming[key] == null && existing[key] != null) merged[key] = existing[key]
  }
  return merged
}

export function historyRowLabels(session = {}, isAdmin = false) {
  const ownerIdentity = session.owner_username || session.owner_user_id || ''
  const ownerName = session.owner_display_name || ownerIdentity
  const owner = isAdmin && ownerName
    ? (ownerIdentity ? `${ownerName}（${ownerIdentity}）` : ownerName)
    : ''

  return {
    source: SOURCE_LABELS[session.source] || session.source || 'Web',
    owner,
    readOnly: session.read_only_on_web === true
  }
}
