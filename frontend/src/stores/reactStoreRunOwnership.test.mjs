import assert from 'node:assert/strict'
import { shouldApplyRunEvent } from './reactStoreRunOwnership.js'

assert.equal(
  shouldApplyRunEvent({ activeRunId: 'run_current', ignoredRunIds: [] }, {
    type: 'streaming_text',
    run_id: 'run_stale',
    data: { run_id: 'run_stale' }
  }),
  false,
  'stale run events should be ignored'
)

assert.equal(
  shouldApplyRunEvent({ activeRunId: 'run_current', ignoredRunIds: [] }, {
    type: 'streaming_text',
    run_id: 'run_current',
    data: { run_id: 'run_current' }
  }),
  true,
  'current run events should be applied'
)

assert.equal(
  shouldApplyRunEvent({ activeRunId: 'run_current', ignoredRunIds: [] }, {
    type: 'start',
    data: { run_id: 'run_new' }
  }),
  true,
  'start events establish a new active run'
)

assert.equal(
  shouldApplyRunEvent({ activeRunId: null, ignoredRunIds: ['run_stale'] }, {
    type: 'complete',
    data: { run_id: 'run_stale' }
  }),
  false,
  'revoked run events should be ignored even when no run is active'
)

console.log('reactStore run ownership tests passed')
