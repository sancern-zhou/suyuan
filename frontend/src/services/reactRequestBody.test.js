import assert from 'node:assert/strict'
import test from 'node:test'

import { buildAnalyzeRequestBody } from './reactRequestBody.js'

test('builds the breaking structured analyze protocol', () => {
  const body = buildAnalyzeRequestBody('分析数据', {
    sessionId: 'query_session_1',
    agentMode: 'query',
    modelTier: 'pro',
    skillIds: ['trend'],
    activeContexts: [{ type: 'skill', id: 'trend' }],
    contextRefs: [{ type: 'conversation_file', resource_id: 'ref-1', display_name: '数据.xlsx' }]
  })

  assert.equal(body.query, '分析数据')
  assert.deepEqual(body.skill_ids, ['trend'])
  assert.deepEqual(body.active_contexts, [{ type: 'skill', id: 'trend' }])
  assert.equal(body.context_refs[0].resource_id, 'ref-1')
  assert.equal(body.model_tier, 'pro')
  assert.equal('attachments' in body, false)
  assert.equal('modelTier' in body, false)
  assert.equal('debug_mode' in body, false)
  assert.equal('skip_auto_followup' in body, false)
})

test('always includes empty selection arrays', () => {
  const body = buildAnalyzeRequestBody('继续', {})
  assert.deepEqual(body.skill_ids, [])
  assert.deepEqual(body.context_refs, [])
  assert.equal(body.active_contexts, null)
})

test('Web assistant uses assistant runtime while professional requests retain their modes', () => {
  assert.equal(buildAnalyzeRequestBody('继续', { agentMode: 'assistant' }).mode, 'assistant')
  assert.equal(buildAnalyzeRequestBody('继续', { agentMode: 'assistant' }).mode, 'assistant')
  for (const mode of ['query', 'expert', 'report', 'ppt', 'board', 'knowledge']) {
    assert.equal(buildAnalyzeRequestBody('继续', { agentMode: mode }).mode, mode)
  }
})

test('carries the previous paused run barrier into the next normal turn', () => {
  const body = buildAnalyzeRequestBody('继续刚才的数据分析', {
    sessionId: 'assistant_session_1',
    previousPausedRunId: 'run_paused_1',
    isInterruption: false
  })

  assert.equal(body.previous_paused_run_id, 'run_paused_1')
  assert.equal(body.is_interruption, false)
})
