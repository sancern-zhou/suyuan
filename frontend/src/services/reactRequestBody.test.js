import assert from 'node:assert/strict'
import test from 'node:test'

import { buildAnalyzeRequestBody } from './reactRequestBody.js'

test('builds the breaking structured analyze protocol', () => {
  const body = buildAnalyzeRequestBody('分析数据', {
    sessionId: 'query_session_1',
    agentMode: 'query',
    modelTier: 'pro',
    skillIds: ['trend'],
    contextRefs: [{ type: 'conversation_file', resource_id: 'ref-1', display_name: '数据.xlsx' }]
  })

  assert.equal(body.query, '分析数据')
  assert.deepEqual(body.skill_ids, ['trend'])
  assert.equal(body.context_refs[0].resource_id, 'ref-1')
  assert.equal(body.model_tier, 'pro')
  assert.equal('attachments' in body, false)
  assert.equal('modelTier' in body, false)
  assert.equal('debug_mode' in body, false)
})

test('always includes empty selection arrays', () => {
  const body = buildAnalyzeRequestBody('继续', {})
  assert.deepEqual(body.skill_ids, [])
  assert.deepEqual(body.context_refs, [])
})
