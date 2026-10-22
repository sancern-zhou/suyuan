import test from 'node:test'
import assert from 'node:assert/strict'
import { replyOutcomes } from './replyOutcomes.js'
const resource = (id, group, format = 'docx', run = 'run1') => ({ resource_id: id, group_id: group, run_id: run, status: 'active', relation: 'primary', role: 'output', kind: 'file', renderer: 'file', format, content_url: `/${id}` })
const message = { id: 'm1', type: 'final', content: '', data: { run_id: 'run1' } }
test('matches only this run and excludes unassigned resources', () => {
  const result = replyOutcomes(message, [message], [resource('a','a'),resource('b','b','docx','old'),resource('c','c','docx','')])
  assert.equal(result.files.length, 1)
})
test('groups multiple document formats into one card', () => {
  const result = replyOutcomes(message, [message], [resource('a','report'), { ...resource('b','report','pdf'), relation: 'rendition', renderer: 'pdf' }])
  assert.equal(result.files.length, 1)
  assert.equal(result.files[0].group.resources.length, 2)
})
test('referenced chart hides its whole group and unreferenced chart is folded', () => {
  const resources = [{ ...resource('a','chart','json'), kind: 'visual', renderer: 'chart', visual_id: 'v1', interactive: true }, { ...resource('b','chart','png'), relation: 'rendition', renderer: 'image', visual_id: 'v1' }]
  assert.equal(replyOutcomes(message, [message], resources).others.length, 1)
  assert.deepEqual(replyOutcomes({ ...message, content: '[[chart:v1]]' }, [], resources), { files: [], others: [] })
})
test('hides data and intermediate files', () => {
  assert.equal(replyOutcomes(message, [message], [resource('a','a','json'), { ...resource('b','b','csv'), kind: 'data' }]).files.length, 0)
})
test('updated report versions retain the owning reply through stable group IDs', () => {
  const final = { ...message, data: { resource_group_ids: ['report'] } }
  assert.equal(replyOutcomes(final, [final], [resource('new','report','docx','resource-edit')]).files.length, 1)
})
