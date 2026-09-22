import test from 'node:test'
import assert from 'node:assert/strict'
import { parseSseChunk } from './workflowSse.js'

test('parseSseChunk parses complete events and keeps partial lines', () => {
  const events = []
  const result = parseSseChunk('data: {"type":"workflow.running"}\n\ndata: {"type":"runtime"}\npar', data => events.push(JSON.parse(data)))
  assert.deepEqual(events, [{ type: 'workflow.running' }])
  assert.equal(result.remainder, 'data: {"type":"runtime"}\npar')
})

test('parseSseChunk ignores comments and empty server events', () => {
  const events = []
  parseSseChunk(': keep-alive\n\n', data => events.push(data))
  assert.deepEqual(events, [])
})
