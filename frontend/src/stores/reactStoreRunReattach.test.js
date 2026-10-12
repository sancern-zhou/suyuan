import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createRunStreamTracker,
  observeRunStreamEvent,
  shouldReportMissingRunProgress
} from './reactStoreRunReattach.js'


test('forwards business events and tracks terminal events', () => {
  const tracker = createRunStreamTracker()

  assert.equal(observeRunStreamEvent(tracker, { type: 'start', data: {} }), true)
  assert.equal(observeRunStreamEvent(tracker, { type: 'thought', data: {} }), true)
  assert.equal(tracker.sawTerminal, false)

  assert.equal(observeRunStreamEvent(tracker, { type: 'complete', data: {} }), true)
  assert.equal(tracker.sawTerminal, true)
})


test('swallows transport events but keeps stream_lost marker', () => {
  const tracker = createRunStreamTracker()

  assert.equal(observeRunStreamEvent(tracker, { type: 'stream_open', data: {} }), false)
  assert.equal(observeRunStreamEvent(tracker, { type: 'stream_closed', data: {} }), false)
  assert.equal(observeRunStreamEvent(tracker, { type: 'stream_lost', data: {} }), false)

  assert.equal(tracker.sawTerminal, false)
  assert.equal(tracker.sawStreamLost, true)
})


test('reports missing progress only when stream ended without terminal and nothing to show', () => {
  const emptyTracker = createRunStreamTracker()
  assert.equal(shouldReportMissingRunProgress(emptyTracker, 0), true)

  const withMessagesTracker = createRunStreamTracker()
  assert.equal(shouldReportMissingRunProgress(withMessagesTracker, 5), false)

  const terminalTracker = createRunStreamTracker()
  observeRunStreamEvent(terminalTracker, { type: 'interrupted', data: {} })
  assert.equal(shouldReportMissingRunProgress(terminalTracker, 0), false)
})


test('every terminal event type is recognized', () => {
  for (const type of ['complete', 'incomplete', 'fatal_error', 'interrupted']) {
    const tracker = createRunStreamTracker()
    observeRunStreamEvent(tracker, { type, data: {} })
    assert.equal(tracker.sawTerminal, true, type)
  }
})
