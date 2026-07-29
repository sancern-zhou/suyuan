import test from 'node:test'
import assert from 'node:assert/strict'

import { restoredConversationPolicy } from './socialHistoryReadOnly.js'

test('social history is read-only and starts a new Web session for new input', () => {
  assert.deepEqual(restoredConversationPolicy({ source: 'social', read_only_on_web: true }), {
    readOnly: true,
    notice: '微信会话历史仅支持查看',
    newConversationRequired: true
  })
})

test('ordinary Web history stays writable', () => {
  assert.equal(restoredConversationPolicy({ source: 'web' }).readOnly, false)
})
