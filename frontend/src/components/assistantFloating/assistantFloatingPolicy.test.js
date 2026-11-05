import assert from 'node:assert/strict'
import test from 'node:test'
import { floatingBadgeCount, isAssistantFloatingRoute } from './assistantFloatingPolicy.js'

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
