import { buildResourceGroups, preferredPreview, targetTab, topLevelProducts } from './resourceGroups.js'

export function chooseRestoredResource(resourceStore, sessionId) {
  if (!sessionId || resourceStore.activeSessionId !== sessionId) return null
  const state = resourceStore.sessionState(sessionId)
  const group = topLevelProducts(buildResourceGroups(state?.resources || []))[0]
  if (!group) return null
  const resource = preferredPreview(group)
  if (!resource) return null
  resourceStore.selectGroup(sessionId, group.group_id)
  resourceStore.selectResource(sessionId, resource.resource_id)
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
