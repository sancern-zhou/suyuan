import test from 'node:test'
import assert from 'node:assert/strict'

import { AGENT_MODES, AGENT_MODE_IDS, getAgentMode } from './agentModes.js'

test('agent mode catalog exposes the six supported modes in product order', () => {
  assert.deepEqual(AGENT_MODE_IDS, [
    'assistant',
    'expert',
    'query',
    'report',
    'chart',
    'ops'
  ])
  assert.deepEqual(AGENT_MODES.map(agent => agent.id), AGENT_MODE_IDS)
})

test('every agent mode provides complete platform copy and presentation metadata', () => {
  for (const agent of AGENT_MODES) {
    assert.ok(agent.name)
    assert.ok(agent.shortName)
    assert.ok(agent.description)
    assert.ok(agent.tags.length > 0)
    assert.ok(agent.accent)
    assert.ok(agent.iconPaths.length > 0)
  }
})

test('agent mode lookup returns matching metadata and null for unsupported modes', () => {
  assert.equal(getAgentMode('query')?.name, '智能问数')
  assert.equal(getAgentMode('missing'), null)
})
