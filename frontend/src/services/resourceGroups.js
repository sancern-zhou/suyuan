const PRODUCT_ROLES = new Set(['output', 'report'])
const PRODUCT_KINDS = new Set(['file', 'artifact', 'visual'])
const SUPPORTED_RENDERERS = new Set([
  'pdf', 'html', 'markdown', 'spreadsheet', 'presentation', 'image', 'chart', 'board'
])
const DOCUMENT_RENDERERS = new Set(['pdf', 'html', 'markdown', 'spreadsheet', 'presentation', 'image'])

const newestFirst = (left, right) => {
  const version = Number(right.version || 0) - Number(left.version || 0)
  if (version) return version
  return new Date(right.updated_at || 0) - new Date(left.updated_at || 0)
}

export function buildResourceGroups(resources = []) {
  const grouped = new Map()
  for (const resource of resources) {
    if (!resource?.group_id) continue
    if (!grouped.has(resource.group_id)) grouped.set(resource.group_id, [])
    grouped.get(resource.group_id).push(resource)
  }

  return [...grouped.entries()].map(([groupId, members]) => {
    const sorted = [...members].sort(newestFirst)
    const primary = sorted.find(resource => resource.relation === 'primary' && resource.status === 'active')
      || sorted.find(resource => resource.relation === 'primary')
      || null
    const versionNumbers = [...new Set(sorted.map(resource => Number(resource.version || 0)))]
      .sort((left, right) => right - left)
    return {
      group_id: groupId,
      primary,
      resources: sorted,
      children: sorted.filter(resource => resource.relation !== 'primary'),
      versions: versionNumbers,
      updated_at: sorted[0]?.updated_at || null
    }
  }).sort((left, right) => new Date(right.updated_at || 0) - new Date(left.updated_at || 0))
}

export function topLevelProducts(groups = []) {
  return groups.filter(({ primary }) => (
    primary?.status === 'active'
    && primary.relation === 'primary'
    && PRODUCT_ROLES.has(primary.role)
    && PRODUCT_KINDS.has(primary.kind)
  ))
}

export function preferredPreview(group) {
  const active = (group?.resources || []).filter(resource => resource.status === 'active')
  return active.find(resource => resource.relation === 'preview' && SUPPORTED_RENDERERS.has(resource.renderer))
    || active.find(resource => resource.relation === 'rendition' && SUPPORTED_RENDERERS.has(resource.renderer))
    || group?.primary
    || null
}

export function targetTab(group) {
  const resource = preferredPreview(group) || group?.primary
  if (!resource) return 'files'
  if (resource.renderer === 'board' || resource.format === 'drawio') return 'board'
  if (resource.renderer === 'chart' || resource.kind === 'visual') return 'visualization'
  if (DOCUMENT_RENDERERS.has(resource.renderer)) return 'document'
  return 'files'
}
