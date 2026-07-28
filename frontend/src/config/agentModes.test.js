import test from 'node:test'
import assert from 'node:assert/strict'

import { AGENT_MODES, AGENT_MODE_IDS, AGENT_PLATFORM_AGENTS, AGENT_PLATFORM_MODE_IDS, getAgentMode } from './agentModes.js'

test('agent mode catalog exposes dedicated ppt, chart and board modes in product order', () => {
  assert.deepEqual(AGENT_MODE_IDS, [
    'assistant',
    'ppt',
    'expert',
    'query',
    'report',
    'chart',
    'board',
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

test('every agent provides complete chat welcome content', () => {
  assert.equal(AGENT_MODES.length, 8)
  for (const agent of AGENT_MODES) {
    assert.ok(agent.welcome?.description)
    assert.ok(agent.welcome?.features.length >= 3)
    assert.ok(agent.welcome?.features.every(feature => feature.trim()))
    assert.ok(agent.welcome?.example)
  }
})

test('agent mode lookup returns matching metadata and null for unsupported modes', () => {
  assert.equal(getAgentMode('query')?.name, 'AI问数智能体')
  assert.equal(getAgentMode('ops')?.welcome.example, '例如："审核这个月1-7日的运维工单"')
  assert.equal(getAgentMode('missing'), null)
})

test('agent platform exposes only environment monitoring and analysis modes', () => {
  assert.deepEqual(AGENT_PLATFORM_MODE_IDS, ['query', 'expert', 'report', 'chart'])
  assert.deepEqual(AGENT_PLATFORM_AGENTS.map(agent => agent.id), AGENT_PLATFORM_MODE_IDS)
  assert.ok(AGENT_PLATFORM_AGENTS.every(agent => AGENT_MODES.includes(agent)))
})
