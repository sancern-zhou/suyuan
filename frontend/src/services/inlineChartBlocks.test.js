import test from 'node:test'
import assert from 'node:assert/strict'
import { inlineChartBlocks } from './inlineChartBlocks.js'

const resources = [{ resource_id: 'r1', visual_id: 'chart1', resource_key: 'chart-spec', interactive: true, status: 'active', content_url: '/spec1' },
  { resource_id: 'r2', visual_id: 'chart2', resource_key: 'chart-spec', interactive: true, status: 'active', content_url: '/spec2' }]
test('keeps chart order and surrounding analysis for restored replies', () => {
  const blocks = inlineChartBlocks('before\n\n[[chart:chart2]]\n\nbetween\n\n[[chart:chart1]]\n\nafter', resources)
  assert.deepEqual(blocks.map(b => b.kind), ['text', 'chart', 'text', 'chart', 'text'])
  assert.deepEqual(blocks.filter(b => b.kind === 'chart').map(b => b.resource.resource_id), ['r2', 'r1'])
  assert.equal(blocks[2].content, '\n\nbetween\n\n')
})
test('supports resource IDs and preserves unresolved or static references', () => {
  const blocks = inlineChartBlocks('[[chart:r1]]\n[[chart:missing]]', resources)
  assert.equal(blocks[0].resource.resource_id, 'r1')
  assert.equal(blocks[1].content, '\n[[chart:missing]]')
})
test('never resolves inactive resources', () => {
  assert.deepEqual(inlineChartBlocks('[[chart:chart1]]', [{ ...resources[0], status: 'deleted' }]), [{ kind: 'text', content: '[[chart:chart1]]' }])
})
test('leaves static image references to the existing image renderer', () => {
  assert.equal(inlineChartBlocks('[[chart:chart1]]', [{ ...resources[0], interactive: false }])[0].kind, 'text')
})

test('matches protocol ids containing dots (e.g. sanitized mathtext names)', () => {
  const resource = { resource_id: 'r1', visual_id: 'generic_pollutant_wind_rose_PM2.5', resource_key: 'chart-spec', interactive: true, status: 'active', content_url: '/c' }
  const blocks = inlineChartBlocks('结论\n\n[[chart:generic_pollutant_wind_rose_PM2.5]]\n', [resource])
  assert.equal(blocks.filter(b => b.kind === 'chart').length, 1)
})
