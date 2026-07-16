import test from 'node:test'
import assert from 'node:assert/strict'

import { AGENT_MODES, AGENT_MODE_IDS, AGENT_SCENES, getAgentMode } from './agentModes.js'

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

test('every non-query agent provides complete chat welcome content', () => {
  const agentsWithWelcome = AGENT_MODES.filter(agent => agent.id !== 'query')

  assert.equal(agentsWithWelcome.length, 5)
  for (const agent of agentsWithWelcome) {
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

test('agent scenes group modes in the requested top-to-bottom order', () => {
  assert.deepEqual(AGENT_SCENES.map(({ id, name, description, modeIds }) => ({
    id,
    name,
    description,
    modeIds
  })), [
    {
      id: 'office',
      name: '办公',
      description: '日常办公与内容创作',
      modeIds: ['assistant', 'chart']
    },
    {
      id: 'monitoring',
      name: '监测分析',
      description: '环境数据研判与成果输出',
      modeIds: ['query', 'expert', 'report']
    },
    {
      id: 'operations',
      name: '运维管理',
      description: '运维处置与任务管理',
      modeIds: ['ops']
    }
  ])
})

test('each agent scene provides a dedicated two-tone line icon', () => {
  for (const scene of AGENT_SCENES) {
    assert.ok(scene.iconPaths.length >= 2)
    assert.ok(scene.iconPaths.some(path => path.tone === 'primary'))
    assert.ok(scene.iconPaths.some(path => path.tone === 'accent'))
    assert.ok(scene.iconPaths.every(path => path.d))
  }
})
