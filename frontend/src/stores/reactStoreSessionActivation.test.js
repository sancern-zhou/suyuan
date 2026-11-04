import assert from 'node:assert/strict'
import test from 'node:test'
import { shouldActivateStartedSession } from './reactStoreSessionActivation.js'

test('start event activates its server session in the active mode', () => {
  assert.equal(shouldActivateStartedSession('start', 'ops_session_123', 'ops', 'ops', null), true)
  assert.equal(shouldActivateStartedSession('complete', 'ops_session_123', 'ops', 'ops', null), false)
})

test('other mode events keep their existing parallel session routing', () => {
  assert.equal(shouldActivateStartedSession('start', 'ops_session_123', 'ops', 'assistant', null), false)
  assert.equal(shouldActivateStartedSession('start', null, 'ops', 'ops', null), false)
  assert.equal(shouldActivateStartedSession('start', 'ops_session_123', 'ops', 'ops', 'ops_session_123'), false)
})
