import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeAssistantSnapshot } from './assistantConversationSync.js'

test('a shared snapshot replaces local turn IDs without duplicating replies', () => {
  const state = { sessionId: 'a', messages: [{ id: 'local', type: 'final', content: 'Done' }] }
  const snapshot = { session_id: 'a', oldest_sequence: 0, messages: [
    { id: 'msg_1', sequence_number: 0, type: 'user', content: 'Question from App' },
    { id: 'msg_2', sequence_number: 1, type: 'final', content: 'Done' }
  ] }
  mergeAssistantSnapshot(state, snapshot)
  mergeAssistantSnapshot(state, snapshot)
  assert.deepEqual(state.messages.map(row => row.id), ['msg_1', 'msg_2'])
})

test('older loaded history and expanded state survive a shared window update', () => {
  const state = { sessionId: 'a', messages: [{ id: 'msg_1', sequence_number: 0 }, { id: 'msg_9', sequence_number: 8, expanded: true }] }
  mergeAssistantSnapshot(state, { session_id: 'a', oldest_sequence: 8, messages: [{ id: 'msg_9', sequence_number: 8 }, { id: 'msg_10', sequence_number: 9 }] })
  assert.deepEqual(state.messages.map(row => row.id), ['msg_1', 'msg_9', 'msg_10'])
  assert.equal(state.messages[1].expanded, true)
})

test('streaming, other conversations, and unchanged snapshots are left alone', () => {
  const state = { sessionId: 'a', isAnalyzing: true, messages: [] }
  assert.equal(mergeAssistantSnapshot(state, { session_id: 'a', messages: [{ id: 'remote' }] }), false)
  state.isAnalyzing = false
  assert.equal(mergeAssistantSnapshot(state, { session_id: 'b', messages: [{ id: 'remote' }] }), false)
  assert.equal(mergeAssistantSnapshot(state, { session_id: 'a', unchanged: true }), false)
  assert.deepEqual(state.messages, [])
})
