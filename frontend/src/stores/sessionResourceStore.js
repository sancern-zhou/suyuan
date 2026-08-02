import { defineStore } from 'pinia'

import { listSessionResources } from '../api/sessionResources.js'

const emptySessionState = () => ({
  resources: [],
  resourceVersion: 0,
  requestedVersion: 0,
  selectedResourceId: null,
  selectedGroupId: null,
  selectionOrigin: null,
  loading: false,
  error: null,
  requestToken: 0
})

const ensureSession = (store, sessionId) => {
  if (!store.sessions[sessionId]) store.sessions[sessionId] = emptySessionState()
  return store.sessions[sessionId]
}

const sessionState = (store, sessionId) => store.sessions[sessionId] || null

const selectedResource = (store, sessionId) => {
  const state = sessionState(store, sessionId)
  if (!state?.selectedResourceId) return null
  return state.resources.find(resource => resource.resource_id === state.selectedResourceId) || null
}

const loadCatalog = async (store, client, sessionId, filters = {}) => {
  if (!sessionId) return null
  const state = ensureSession(store, sessionId)
  const token = state.requestToken + 1
  state.requestToken = token
  state.loading = true
  state.error = null

  const resources = []
  let cursor = null
  let resourceVersion = 0
  const { minimumVersion = 0, ...queryFilters } = filters
  try {
    do {
      const page = await client.listResources(sessionId, {
        ...queryFilters,
        limit: queryFilters.limit || 200,
        ...(cursor ? { cursor } : {})
      })
      if (store.sessions[sessionId]?.requestToken !== token) return null
      resources.push(...(Array.isArray(page?.resources) ? page.resources : []))
      resourceVersion = Math.max(resourceVersion, Number(page?.resource_version || 0))
      cursor = page?.next_cursor || null
    } while (cursor)

    if (store.sessions[sessionId]?.requestToken !== token) return null
    state.resources = resources
    state.resourceVersion = Math.max(resourceVersion, Number(minimumVersion || 0))
    state.requestedVersion = state.resourceVersion
    state.loading = false
    return state
  } catch (error) {
    if (store.sessions[sessionId]?.requestToken === token) {
      state.loading = false
      state.error = error instanceof Error ? error.message : String(error)
      state.requestedVersion = state.resourceVersion
    }
    throw error
  }
}

const refreshIfNewer = async (store, client, sessionId, resourceVersion) => {
  const state = ensureSession(store, sessionId)
  const version = Number(resourceVersion || 0)
  if (version <= Math.max(state.resourceVersion, state.requestedVersion)) return state
  state.requestedVersion = version
  return loadCatalog(store, client, sessionId, { minimumVersion: version })
}

const createActions = (store, client) => ({
  sessionState: sessionId => sessionState(store, sessionId),
  selectedResource: sessionId => selectedResource(store, sessionId),
  loadCatalog: (sessionId, filters = {}) => loadCatalog(store, client, sessionId, filters),
  refreshIfNewer: (sessionId, version) => refreshIfNewer(store, client, sessionId, version),
  onResourcesChanged: event => {
    if (!event?.session_id) return null
    return refreshIfNewer(store, client, event.session_id, event.resource_version)
  },
  selectResource: (sessionId, resourceId, origin = 'product') => {
    const state = ensureSession(store, sessionId)
    state.selectedResourceId = resourceId || null
    state.selectionOrigin = resourceId ? origin : null
  },
  selectGroup: (sessionId, groupId) => {
    ensureSession(store, sessionId).selectedGroupId = groupId || null
  },
  activateSession: sessionId => {
    const previous = store.activeSessionId
    if (previous && previous !== sessionId && store.sessions[previous]?.selectionOrigin === 'explicit') {
      store.sessions[previous].selectedResourceId = null
      store.sessions[previous].selectedGroupId = null
      store.sessions[previous].selectionOrigin = null
    }
    store.activeSessionId = sessionId || null
    if (sessionId) ensureSession(store, sessionId)
  },
  clearSession: sessionId => {
    if (!store.sessions[sessionId]) return
    store.sessions[sessionId].requestToken += 1
    delete store.sessions[sessionId]
    if (store.activeSessionId === sessionId) store.activeSessionId = null
  }
})

export const createResourceStoreHarness = ({ listResources = listSessionResources } = {}) => {
  const store = { activeSessionId: null, sessions: {} }
  return Object.assign(store, createActions(store, { listResources }))
}

export const useSessionResourceStore = defineStore('sessionResources', {
  state: () => ({ activeSessionId: null, sessions: {} }),
  getters: {
    activeSessionState: state => state.activeSessionId ? state.sessions[state.activeSessionId] || null : null
  },
  actions: {
    sessionState(sessionId) { return sessionState(this, sessionId) },
    selectedResource(sessionId) { return selectedResource(this, sessionId) },
    loadCatalog(sessionId, filters = {}) {
      return loadCatalog(this, { listResources: listSessionResources }, sessionId, filters)
    },
    refreshIfNewer(sessionId, version) {
      return refreshIfNewer(this, { listResources: listSessionResources }, sessionId, version)
    },
    onResourcesChanged(event) {
      if (!event?.session_id) return null
      return this.refreshIfNewer(event.session_id, event.resource_version)
    },
    selectResource(sessionId, resourceId, origin = 'product') {
      const state = ensureSession(this, sessionId)
      state.selectedResourceId = resourceId || null
      state.selectionOrigin = resourceId ? origin : null
    },
    selectGroup(sessionId, groupId) {
      ensureSession(this, sessionId).selectedGroupId = groupId || null
    },
    activateSession(sessionId) {
      const previous = this.activeSessionId
      if (previous && previous !== sessionId && this.sessions[previous]?.selectionOrigin === 'explicit') {
        this.sessions[previous].selectedResourceId = null
        this.sessions[previous].selectedGroupId = null
        this.sessions[previous].selectionOrigin = null
      }
      this.activeSessionId = sessionId || null
      if (sessionId) ensureSession(this, sessionId)
    },
    clearSession(sessionId) {
      if (!this.sessions[sessionId]) return
      this.sessions[sessionId].requestToken += 1
      delete this.sessions[sessionId]
      if (this.activeSessionId === sessionId) this.activeSessionId = null
    }
  }
})
