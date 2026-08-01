import assert from 'node:assert/strict'
import test from 'node:test'

import { createResourceStoreHarness } from '../stores/sessionResourceStore.js'
import {
  applyResourceStreamEvent,
  chooseRestoredResource,
  restoreSessionResources
} from './sessionResourceLifecycle.js'

const resource = (overrides = {}) => ({
  resource_id: 'report', group_id: 'report-group', relation: 'primary',
  kind: 'file', role: 'report', renderer: 'file', format: 'docx', status: 'active',
  version: 1, updated_at: '2026-08-01T10:00:00Z',
  ...overrides
})

test('restores the catalog and selects the newest previewable product', async () => {
  const store = createResourceStoreHarness({
    listResources: async sessionId => ({
      session_id: sessionId,
      resource_version: 3,
      resources: [
        resource(),
        resource({ resource_id: 'pdf', relation: 'preview', renderer: 'pdf', format: 'pdf' }),
        resource({ resource_id: 'chart', group_id: 'chart-group', kind: 'visual', role: 'output', renderer: 'chart', updated_at: '2026-08-01T11:00:00Z' })
      ]
    })
  })

  const restored = await restoreSessionResources(store, 'session-a', 3)

  assert.equal(store.activeSessionId, 'session-a')
  assert.equal(restored.targetTab, 'visualization')
  assert.equal(store.selectedResource('session-a').resource_id, 'chart')
})

test('does not apply restored selection after the active session changes', async () => {
  let resolveCatalog
  const store = createResourceStoreHarness({
    listResources: async sessionId => new Promise(resolve => { resolveCatalog = () => resolve({ session_id: sessionId, resource_version: 1, resources: [resource()] }) })
  })

  const restoring = restoreSessionResources(store, 'session-a', 1)
  store.activateSession('session-b')
  resolveCatalog()

  assert.equal(await restoring, null)
  assert.equal(store.activeSessionId, 'session-b')
  assert.equal(store.selectedResource('session-a'), null)
})

test('delegates only unified resource change events to the catalog store', async () => {
  const events = []
  const store = { onResourcesChanged: async event => events.push(event) }

  await applyResourceStreamEvent(store, { type: 'resources_changed', data: { session_id: 'session-a', resource_version: 4 } })
  await applyResourceStreamEvent(store, { type: 'complete', data: { session_id: 'session-a' } })

  assert.deepEqual(events, [{ session_id: 'session-a', resource_version: 4 }])
})

test('chooseRestoredResource returns no preview for an empty catalog', () => {
  const store = createResourceStoreHarness()
  store.activateSession('session-a')
  assert.equal(chooseRestoredResource(store, 'session-a'), null)
})
