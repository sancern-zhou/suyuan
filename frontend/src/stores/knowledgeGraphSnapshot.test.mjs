import assert from 'node:assert/strict'
import test from 'node:test'

import { collectGraphSnapshot } from './knowledgeGraphSnapshot.js'

test('collectGraphSnapshot follows every cursor and returns only a complete snapshot', async () => {
  const calls = []
  const pages = [
    { snapshot_version: 4, entities: [{ id: 'e1' }], relations: [], next_cursor: 'c1', entity_total: 2, relation_total: 1 },
    { snapshot_version: 4, entities: [{ id: 'e2' }], relations: [], next_cursor: 'c2', entity_total: 2, relation_total: 1 },
    { snapshot_version: 4, entities: [], relations: [{ id: 'r1' }], next_cursor: null, entity_total: 2, relation_total: 1 }
  ]
  const result = await collectGraphSnapshot(async params => {
    calls.push(params)
    return pages[calls.length - 1]
  }, { statuses: ['confirmed'] })

  assert.deepEqual(result.entities.map(item => item.id), ['e1', 'e2'])
  assert.deepEqual(result.relations.map(item => item.id), ['r1'])
  assert.equal(calls[1].snapshotVersion, 4)
  assert.equal(calls[2].cursor, 'c2')
})

test('collectGraphSnapshot restarts once when snapshot changes', async () => {
  let call = 0
  const result = await collectGraphSnapshot(async () => {
    call += 1
    if (call === 1) return { snapshot_version: 1, entities: [{ id: 'old' }], relations: [], next_cursor: 'next', entity_total: 1, relation_total: 0 }
    if (call === 2) { const error = new Error('changed'); error.status = 409; error.code = 'graph_snapshot_changed'; throw error }
    return { snapshot_version: 2, entities: [{ id: 'new' }], relations: [], next_cursor: null, entity_total: 1, relation_total: 0 }
  }, { statuses: ['confirmed'] })

  assert.deepEqual(result.entities.map(item => item.id), ['new'])
  assert.equal(call, 3)
})
