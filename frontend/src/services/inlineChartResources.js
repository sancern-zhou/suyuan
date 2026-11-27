export function inlineChartKind(resource) {
  if (resource?.resource_key === 'chart-spec') {
    return resource.interactive === false ? null : 'spec'
  }
  if (resource?.renderer === 'image' || resource?.media_type?.startsWith('image/')) {
    return 'image'
  }
  return null
}

function chartContentUrl(resource, scope, ownerId, apiBaseUrl) {
  // Only use a URL supplied by the authorized catalog for this exact member.
  // Keep its query (including preview tickets) and let authFetch apply the gateway base.
  const parts = resource.content_url?.match(/^([^?#]+)(\?[^#]*)?$/)
  if (!parts) return null
  const memberPath = `/${scope}/${encodeURIComponent(ownerId)}/resources/${resource.resource_id}/content`
  const prefixes = ['/api', '/api/suyuan', apiBaseUrl?.replace(/\/$/, '')]
  if (!prefixes.some(prefix => prefix && parts[1] === `${prefix}${memberPath}`)) return null
  return `/api${memberPath}${parts[2] || ''}`
}

export function indexInlineChartResources(resources, scope, ownerId, apiBaseUrl = import.meta.env?.VITE_API_BASE_URL) {
  const index = new Map()
  if (!ownerId) return index
  for (const resource of resources || []) {
    if (resource?.status !== 'active') continue
    const kind = inlineChartKind(resource)
    if (!kind) continue
    const url = chartContentUrl(resource, scope, ownerId, apiBaseUrl)
    if (!url) continue
    index.set(resource.resource_id, { kind, resource, url })
  }
  return index
}
