import assert from 'node:assert/strict'
import test from 'node:test'
import { floatingBadgeCount, isAssistantFloatingRoute, nextUnreadFocus } from './assistantFloatingPolicy.js'

test('floating assistant requires project flag, authentication and a regular route', () => {
  assert.equal(isAssistantFloatingRoute({ name: 'knowledge-base', meta: {}, query: {} }, true, true), true)
  assert.equal(isAssistantFloatingRoute({ name: 'login', meta: { public: true }, query: {} }, true, true), false)
  assert.equal(isAssistantFloatingRoute({ name: 'bigscreen', meta: { allowDashboardToken: true }, query: {} }, true, true), false)
  assert.equal(isAssistantFloatingRoute({ name: 'analysis', meta: {}, query: { embed: '1' } }, true, true), false)
  assert.equal(isAssistantFloatingRoute({ name: 'analysis', meta: {}, query: {} }, false, true), false)
  assert.equal(isAssistantFloatingRoute({ name: 'analysis', meta: {}, query: {} }, true, false), false)
})

test('conversation badge does not double-count notification unread watermarks', () => {
  assert.equal(floatingBadgeCount([{ unread_count: 2 }, { unread_count: 3 }, {}]), 5)
  assert.equal(floatingBadgeCount([]), 0)
})

test('unread focus stays on the current session when it already carries the unread', () => {
  const rows = [
    { session_id: 'b', unread_count: 1 },
    { session_id: 'a', unread_count: 0 },
  ]
  assert.equal(nextUnreadFocus(rows, 'b'), null)
  assert.equal(nextUnreadFocus(rows, 'a')?.session_id, 'b')
  assert.equal(nextUnreadFocus([], 'a'), null)
  assert.equal(nextUnreadFocus([{ session_id: 'a', unread_count: 0 }], 'a'), null)
})

test('unread focus picks the most recently updated unread conversation for fresh states', () => {
  // 会话列表按 last_message_at 倒序，取第一个未读行即最近更新的未读会话。
  const rows = [
    { session_id: 'c', unread_count: 0 },
    { session_id: 'b', unread_count: 2 },
    { session_id: 'a', unread_count: 1 },
  ]
  assert.equal(nextUnreadFocus(rows, null)?.session_id, 'b')
  assert.equal(nextUnreadFocus(rows)?.session_id, 'b')
})
