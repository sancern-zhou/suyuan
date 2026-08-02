import { buildResourceGroups, preferredPreview, targetTab, topLevelProducts } from './resourceGroups.js'

export function chooseRestoredResource(resourceStore, sessionId) {
  if (!sessionId || resourceStore.activeSessionId !== sessionId) return null
  const state = resourceStore.sessionState(sessionId)
  const productGroups = topLevelProducts(buildResourceGroups(state?.resources || []))
  const selected = resourceStore.selectedResource(sessionId)
  if (selected?.status === 'active') {
    const allGroups = buildResourceGroups(state?.resources || [])
    const group = allGroups.find(item => item.group_id === selected.group_id)
    const isExplicitAttachment = state?.selectionOrigin === 'explicit' && selected.role === 'attachment'
    if (group && (isExplicitAttachment || productGroups.some(item => item.group_id === group.group_id))) {
      resourceStore.selectGroup(sessionId, group.group_id)
      return { group, resource: selected, targetTab: targetTab(group) }
    }
  }
  const retainedGroup = state?.selectedGroupId
    ? productGroups.find(item => item.group_id === state.selectedGroupId)
    : null
  if (retainedGroup) {
    const resource = preferredPreview(retainedGroup)
    if (resource) {
      resourceStore.selectResource(
        sessionId,
        resource.resource_id,
        state.selectionOrigin || 'auto'
      )
      return { group: retainedGroup, resource, targetTab: targetTab(retainedGroup) }
    }
  }
  const group = productGroups[0]
  if (!group) return null
  const resource = preferredPreview(group)
  if (!resource) return null
  resourceStore.selectGroup(sessionId, group.group_id)
  resourceStore.selectResource(sessionId, resource.resource_id, 'auto')
  return { group, resource, targetTab: targetTab(group) }
}

export async function restoreSessionResources(resourceStore, sessionId, expectedVersion = 0) {
  if (!sessionId) return null
  resourceStore.activateSession(sessionId)
  await resourceStore.loadCatalog(sessionId, { minimumVersion: expectedVersion })
  if (resourceStore.activeSessionId !== sessionId) return null
  await resourceStore.refreshIfNewer(sessionId, expectedVersion)
  return chooseRestoredResource(resourceStore, sessionId)
}

export function applyResourceStreamEvent(resourceStore, event) {
  if (event?.type !== 'resources_changed') return null
  const payload = event.data || event
  if (!payload?.session_id) return null
  return resourceStore.onResourcesChanged(payload)
}
