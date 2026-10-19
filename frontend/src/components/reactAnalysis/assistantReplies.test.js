import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeAssistantReplies } from './assistantReplies.js'

const reply = { message_id: 'execution:a', source_session_id: 's', delivery_state: 'inbox_saved', content: 'Done', transcript_message_id: 'msg_7' }
test('new replies appear once and retain persisted message identity', () => {
  const state = { sessionId: 's', messages: [] }
  mergeAssistantReplies(state, [reply])
  mergeAssistantReplies(state, [reply])
  assert.equal(state.messages.length, 1)
  assert.equal(state.messages[0].id, 'msg_7')
  assert.equal(state.messages[0].data.notification_id, 'execution:a')
})
test('streaming and other sessions are left intact', () => {
  for (const state of [{ sessionId: 'other', messages: [] }, { sessionId: 's', messages: [], isAnalyzing: true }]) {
    assert.deepEqual(mergeAssistantReplies(state, [reply]), [])
    assert.deepEqual(state.messages, [])
  }
})
test('undelivered replies are not inserted as if delivered', () => {
  const state = { sessionId: 's', messages: [] }
  mergeAssistantReplies(state, [{ ...reply, delivery_state: 'pending' }])
  assert.equal(state.messages.length, 0)
})
