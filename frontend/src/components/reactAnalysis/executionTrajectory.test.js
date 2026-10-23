import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildTrajectoryEntries, mergeTrajectoryMessages } from './executionTrajectory.js'

test('pairs tool requests and results by call id even when completions arrive out of order', () => {
  const entries = buildTrajectoryEntries([
    { type: 'tool_use', data: { tool_use_id: 'a', tool_name: 'query', input: { city: '南昌' } } },
    { type: 'tool_use', data: { tool_use_id: 'b', tool_name: 'chart' } },
    { type: 'tool_result', data: { tool_use_id: 'b', result: { success: false, error: 'failed' } } },
    { type: 'tool_result', data: { tool_use_id: 'a', result: { value: 42 } } }
  ])
  assert.equal(entries.length, 2)
  assert.deepEqual(entries[0].input, { city: '南昌' })
  assert.deepEqual(entries[0].result, { value: 42 })
  assert.equal(entries[0].status, '已完成')
  assert.equal(entries[1].status, '失败')
})

test('full historical payload survives abbreviated restore and duplicate live tool events', () => {
  const saved = [{ id: 'db', sequence_number: 1, type: 'tool_use', content: 'full', data: { tool_use_id: 'a', input: { value: 1 } } }]
  const live = [{ id: 'live', type: 'tool_use', content_preview: 'preview', content: 'preview', data: { tool_use_id: 'a', tool_name: 'query' } }]
  const merged = mergeTrajectoryMessages(saved, live)
  assert.equal(merged.length, 1)
  assert.equal(merged[0].content, 'full')
  assert.deepEqual(merged[0].data.input, { value: 1 })
  assert.equal(merged[0].data.tool_name, 'query')
})

test('orphan results remain readable and reused ids do not attach results to an earlier turn', () => {
  const entries = buildTrajectoryEntries([
    { type: 'tool_use', data: { tool_use_id: 'a' } },
    { type: 'user', content: 'new turn' },
    { type: 'tool_result', data: { tool_use_id: 'a', result: { text: 'restored output' } } }
  ])
  assert.equal(entries[0].result, undefined)
  assert.deepEqual(entries[2].result, { text: 'restored output' })
})
