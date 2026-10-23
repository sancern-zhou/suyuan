import { test } from 'node:test'
import assert from 'node:assert/strict'
import { modelTrajectoryCards, mergeModelRecords, trajectoryUsage } from './modelTrajectory.js'

test('main calls show input deltas while compact and replaced contexts remain complete', () => {
  const user = { role: 'user', content: 'question' }
  const assistant = { role: 'assistant', content: 'answer' }
  const tool = { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'a', content: 'result' }] }
  const cards = modelTrajectoryCards([
    { request_id: '1', session_id: 'a', source: 'main', request: { system: 'system', messages: [user] } },
    { request_id: '2', session_id: 'a', source: 'main', request: { system: 'system', messages: [user, assistant, tool] } },
    { request_id: '3', session_id: 'a', source: 'compact', request: { messages: [{ role: 'user', content: 'summarize' }] } },
    { request_id: '4', session_id: 'a', source: 'main', request: { system: 'changed system', messages: [{ role: 'user', content: 'compressed history' }] } }
  ])
  assert.equal(cards[0].rows.length, 2)
  assert.equal(cards[1].rows.length, 1)
  assert.equal(cards[1].rows[0].kind, 'tool')
  assert.equal(cards[2].rows[0].text, 'summarize')
  assert.equal(cards[3].rows[0].text, 'changed system')
})

test('polling replaces running records without dropping older loaded pages', () => {
  const records = mergeModelRecords([{ request_id: '1', status: 'completed' }, { request_id: '2', status: 'running' }], [{ request_id: '2', status: 'completed' }])
  assert.equal(records.length, 2)
  assert.equal(records[1].status, 'completed')
})

test('Anthropic cache tokens add to total while chat cache tokens are included in input', () => {
  const response = { usage: { input_tokens: 20, output_tokens: 5, cache_read_input_tokens: 10 } }
  assert.equal(trajectoryUsage({ response, token_usage_mode: 'anthropic' }).total, 35)
  assert.equal(trajectoryUsage({ response, token_usage_mode: 'chat_completions' }).total, 25)
})
