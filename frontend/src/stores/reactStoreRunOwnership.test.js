import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldApplyRunEvent } from './reactStoreRunOwnership.js'


test('rejects even a late start event from an explicitly ignored paused run', () => {
  const state = {
    activeRunId: null,
    ignoredRunIds: ['run_paused']
  }

  assert.equal(shouldApplyRunEvent(state, {
    type: 'start',
    data: { run_id: 'run_paused' }
  }), false)
})


test('accepts the start event for the new run after a pause', () => {
  const state = {
    activeRunId: null,
    ignoredRunIds: ['run_paused']
  }

  assert.equal(shouldApplyRunEvent(state, {
    type: 'start',
    data: { run_id: 'run_new' }
  }), true)
})
