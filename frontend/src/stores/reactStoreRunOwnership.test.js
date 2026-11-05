import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldApplyRunEvent, shouldClearPendingPausedRunId } from './reactStoreRunOwnership.js'


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


test('clears pending paused run id only on pause checkpoint failure', () => {
  assert.equal(shouldClearPendingPausedRunId({
    code: 'pause_checkpoint_failed',
    error: '暂停记录保存失败，请重试当前消息'
  }), true)

  assert.equal(shouldClearPendingPausedRunId({ code: 'session_run_in_progress' }), false)
  assert.equal(shouldClearPendingPausedRunId({}), false)
  assert.equal(shouldClearPendingPausedRunId(null), false)
})
