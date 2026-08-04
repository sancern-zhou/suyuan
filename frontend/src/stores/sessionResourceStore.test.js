import assert from 'node:assert/strict'
import test from 'node:test'

import { createResourceStoreHarness } from './sessionResourceStore.js'

const page = (sessionId, version, resources, nextCursor = null) => ({
  session_id: sessionId,
  resource_version: version,
  resources,
  next_cursor: nextCursor
})

test('isolates catalog and selection state by session', async () => {
  const store = createResourceStoreHarness({
    listResources: async (sessionId) => page(sessionId, 1, [{ resource_id: `resource-${sessionId}` }])
  })

  await store.loadCatalog('session-a')
  store.selectResource('session-a', 'resource-session-a')
  await store.loadCatalog('session-b')

  assert.equal(store.selectedResource('session-a').resource_id, 'resource-session-a')
  assert.equal(store.selectedResource('session-b'), null)
})

test('clears an explicit attachment selection when switching sessions', async () => {
  const store = createResourceStoreHarness({
    listResources: async sessionId => page(sessionId, 1, [{ resource_id: `resource-${sessionId}` }])
  })
  store.activateSession('session-a')
  await store.loadCatalog('session-a')
  store.selectResource('session-a', 'resource-session-a', 'explicit')

  store.activateSession('session-b')

  assert.equal(store.sessionState('session-a').selectedResourceId, null)
  assert.equal(store.sessionState('session-a').selectionOrigin, null)
})

test('refreshes once for a newer event and ignores out-of-order versions', async () => {
  const fetches = new Map()
  const store = createResourceStoreHarness({
    listResources: async (sessionId) => {
      fetches.set(sessionId, (fetches.get(sessionId) || 0) + 1)
      return page(sessionId, fetches.get(sessionId) === 1 ? 1 : 4, [])
    }
  })

  await store.loadCatalog('session-a')
  await store.onResourcesChanged({ session_id: 'session-a', resource_version: 4 })
  await store.onResourcesChanged({ session_id: 'session-a', resource_version: 3 })

  assert.equal(fetches.get('session-a'), 2)
  assert.equal(store.sessionState('session-a').resourceVersion, 4)
})

test('records a one-shot presentation request for publish_session_file events', async () => {
  const resource = {
    resource_id: 'published-file',
    group_id: 'published-group',
    status: 'active'
  }
  const store = createResourceStoreHarness({
    listResources: async sessionId => page(sessionId, 2, [resource])
  })

  await store.onResourcesChanged({
    session_id: 'session-a',
    resource_version: 2,
    focus_resource_id: 'published-file'
  })

  assert.deepEqual(store.sessionState('session-a').presentationRequest, {
    resourceId: 'published-file',
    resourceVersion: 2
  })
  assert.deepEqual(
    store.consumePresentationRequest('session-a', 'published-file'),
    { resourceId: 'published-file', resourceVersion: 2 }
  )
  assert.equal(store.sessionState('session-a').presentationRequest, null)
})

test('retries until the catalog reports the expected version without another event', async () => {
  let fetchCount = 0
  const store = createResourceStoreHarness({
    listResources: async sessionId => {
      fetchCount += 1
      if (fetchCount < 3) return page(sessionId, 2, [{ resource_id: 'old' }])
      return page(sessionId, 3, [{ resource_id: 'new' }])
    }
  })

  await store.loadCatalog('session-a')
  await store.onResourcesChanged({ session_id: 'session-a', resource_version: 3 })

  assert.equal(fetchCount, 3)
  assert.equal(store.sessionState('session-a').resourceVersion, 3)
  assert.deepEqual(store.sessionState('session-a').resources, [{ resource_id: 'new' }])
})

test('does not replace an observed catalog with an older snapshot', async () => {
  let fetchCount = 0
  const store = createResourceStoreHarness({
    listResources: async sessionId => {
      fetchCount += 1
      return fetchCount === 1
        ? page(sessionId, 4, [{ resource_id: 'current' }])
        : page(sessionId, 3, [{ resource_id: 'obsolete' }])
    }
  })

  await store.loadCatalog('session-a')
  await store.loadCatalog('session-a')

  assert.equal(store.sessionState('session-a').resourceVersion, 4)
  assert.deepEqual(store.sessionState('session-a').resources, [{ resource_id: 'current' }])
})

test('ignores an older event while a newer version refresh is still in flight', async () => {
  let resolveRefresh
  let fetchCount = 0
  const refresh = new Promise(resolve => { resolveRefresh = resolve })
  const store = createResourceStoreHarness({
    listResources: async sessionId => {
      fetchCount += 1
      if (fetchCount === 1) return page(sessionId, 1, [])
      return refresh
    }
  })

  await store.loadCatalog('session-a')
  const newer = store.onResourcesChanged({ session_id: 'session-a', resource_version: 4 })
  const older = store.onResourcesChanged({ session_id: 'session-a', resource_version: 3 })
  assert.equal(fetchCount, 2)
  resolveRefresh(page('session-a', 4, []))
  await Promise.all([newer, older])
})

test('loads every page and atomically replaces the catalog', async () => {
  const store = createResourceStoreHarness({
    listResources: async (sessionId, filters) => filters.cursor
      ? page(sessionId, 2, [{ resource_id: 'second' }])
      : page(sessionId, 2, [{ resource_id: 'first' }], 'next')
  })

  await store.loadCatalog('session-a')

  assert.deepEqual(
    store.sessionState('session-a').resources.map(resource => resource.resource_id),
    ['first', 'second']
  )
})

test('discards a stale response after a newer request token wins', async () => {
  let resolveFirst
  let requestCount = 0
  const first = new Promise(resolve => { resolveFirst = resolve })
  const store = createResourceStoreHarness({
    listResources: async (sessionId) => {
      requestCount += 1
      if (requestCount === 1) return first
      return page(sessionId, 3, [{ resource_id: 'new' }])
    }
  })

  const staleLoad = store.loadCatalog('session-a')
  await store.loadCatalog('session-a')
  resolveFirst(page('session-a', 2, [{ resource_id: 'old' }]))
  await staleLoad

  assert.deepEqual(
    store.sessionState('session-a').resources.map(resource => resource.resource_id),
    ['new']
  )
})
