import { buildResourceGroups, preferredPreview, targetTab, topLevelProducts } from './resourceGroups.js'

const timestamp = value => {
  const parsed = new Date(value || 0).getTime()
  return Number.isFinite(parsed) ? parsed : 0
}

const firstProducedAt = group => {
  const members = group?.resources || []
  const created = members.map(item => timestamp(item.created_at)).filter(Boolean)
  if (created.length) return Math.min(...created)
  const updated = members.map(item => timestamp(item.updated_at)).filter(Boolean)
  return updated.length ? Math.min(...updated) : 0
}

export function visualizationGalleryItems(resources = [], includeResourceId = '') {
  const allGroups = buildResourceGroups(resources)
  const groups = topLevelProducts(allGroups)
  if (includeResourceId) {
    const attachmentGroup = allGroups.find(group => group.resources.some(
      resource => resource.resource_id === includeResourceId
    ))
    if (attachmentGroup && !groups.some(group => group.group_id === attachmentGroup.group_id)) {
      groups.push(attachmentGroup)
    }
  }
  return groups
    .filter(group => targetTab(group) === 'visualization')
    .map(group => ({
      group,
      resource: preferredPreview(group),
      firstProducedAt: firstProducedAt(group)
    }))
    .filter(item => item.resource)
    .sort((left, right) => (
      left.firstProducedAt - right.firstProducedAt
      || String(left.group.group_id).localeCompare(String(right.group.group_id))
    ))
}
