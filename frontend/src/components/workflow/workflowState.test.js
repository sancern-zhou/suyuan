import assert from 'node:assert/strict'
import test from 'node:test'
import { workflowCanResume, workflowGaps } from './workflowState.js'

test('partial delivery exposes gaps without allowing exhausted retries', () => {
  const snapshot = { status: 'partial', delivery: { gaps: [{ task_id: 'weather', reason: 'missing' }], retryable_nodes: [] } }
  assert.deepEqual(workflowGaps(snapshot), snapshot.delivery.gaps)
  assert.equal(workflowCanResume(snapshot), false)
  snapshot.delivery.retryable_nodes.push('weather')
  assert.equal(workflowCanResume(snapshot), true)
  snapshot.budget_state = { exhausted: 'max_retries' }
  assert.equal(workflowCanResume(snapshot), false)
})

test('legacy snapshots retain failed and blocked evidence gaps', () => {
  const snapshot = { status: 'failed', graph: { air: { status: 'succeeded' }, weather: { status: 'failed' }, analysis: { status: 'blocked' }, skip: { status: 'skipped' } },
    runtime: { runs: { w: { parent_task_id: 'flow', task_id: 'weather', status: 'failed', attempt: 1, max_attempts: 2 } } } }
  assert.deepEqual(workflowGaps(snapshot).map(gap => gap.task_id), ['weather', 'analysis'])
  assert.equal(workflowCanResume(snapshot), true)
  snapshot.node_retryable = { weather: false }
  assert.equal(workflowCanResume(snapshot), false)
})
