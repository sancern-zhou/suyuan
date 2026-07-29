import assert from 'node:assert/strict'
import test from 'node:test'

import { filterGraphData, findEntityMatches, stableTypeColor, toG6Data } from './knowledgeGraphData.js'

test('toG6Data preserves isolated nodes self loops and parallel relations', () => {
  const entities = [
    { id: 'a', name: 'Alpha', entity_type: 'Device' },
    { id: 'b', name: 'Beta', entity_type: 'Device' },
    { id: 'isolated', name: 'Alone', entity_type: 'Place' }
  ]
  const relations = [
    { id: 'loop', source_entity_id: 'a', target_entity_id: 'a', relation_type: 'SELF' },
    { id: 'p1', source_entity_id: 'a', target_entity_id: 'b', relation_type: 'LINK' },
    { id: 'p2', source_entity_id: 'a', target_entity_id: 'b', relation_type: 'BACKUP' }
  ]
  const graph = toG6Data(entities, relations)
  assert.equal(graph.nodes.length, 3)
  assert.equal(graph.edges.length, 3)
  assert.equal(graph.nodes.find(node => node.id === 'a').data.degree, 4)
  assert.equal(graph.nodes.find(node => node.id === 'isolated').data.degree, 0)
  assert.equal(stableTypeColor('Device'), stableTypeColor('Device'))
})

test('filters and searches without mutating source data', () => {
  const graph = toG6Data(
    [{ id: 'a', name: 'Alpha', entity_type: 'Device' }, { id: 'b', name: 'Beta', entity_type: 'Place' }],
    [{ id: 'r', source_entity_id: 'a', target_entity_id: 'b', relation_type: 'LOCATED_IN' }]
  )
  const filtered = filterGraphData(graph, { entityTypes: new Set(['Device']), relationTypes: new Set() })
  assert.deepEqual(filtered.nodes.map(node => node.id), ['a'])
  assert.equal(filtered.edges.length, 0)
  assert.deepEqual(findEntityMatches(graph, 'alp'), ['a'])
  assert.equal(graph.nodes.length, 2)
})
