import test from 'node:test'
import assert from 'node:assert/strict'
import { prependHistory, loadHistoryPage } from './historyPagination.js'

const state = id => ({ sessionId: id, messages: [], pagination: { hasMoreMessages: true, loadingMore: false, oldestSequence: 10 } })

test('a switched session receives no messages or loading updates from another session', async () => {
  const a = state('A'), b = state('B')
  let finish
  const pending = loadHistoryPage(a, () => new Promise(resolve => { finish = resolve }), () => true)
  let current = b
  finish({ messages: [{ id: 'A-history', sequence_number: 1, content: '继续' }], has_more: false, total_count: 1 })
  await pending
  assert.equal(current.messages.length, 0)
  assert.equal(a.messages[0].id, 'A-history')
  assert.equal(a.pagination.loadingMore, false)
})

test('identical text is retained and overlapping pages deduplicate by sequence', () => {
  const a = state('A')
  a.messages = [{ id: 'new', sequence_number: 4, content: '继续' }]
  prependHistory(a, [{ id: 'old', sequence_number: 1, content: '继续' }, { id: 'other-id', sequence_number: 4, content: '继续' }])
  assert.deepEqual(a.messages.map(m => m.sequence_number), [1, 4])
  a.pagination.oldestSequence = 10
  prependHistory(a, [{ id: 'old', sequence_number: 1, content: '继续' }])
  assert.equal(a.pagination.oldestSequence, 1)
})

test('an account reset invalidates the pending history result', async () => {
  const a = state('A')
  await loadHistoryPage(a, async () => ({ messages: [{ id: 'private' }], has_more: false }), () => false)
  assert.equal(a.messages.length, 0)
  assert.equal(a.pagination.loadingMore, false)
})
