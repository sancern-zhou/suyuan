import test from 'node:test'
import assert from 'node:assert/strict'

import { AGENT_MODES, AGENT_MODE_IDS, AGENT_SCENES, getAgentMode, selectAgentModes } from './agentModes.js'

test('agent mode catalog exposes dedicated ppt, chart and board modes in product order', () => {
  assert.deepEqual(AGENT_MODE_IDS, [
    'assistant',
    'ppt',
    'expert',
    'query',
    'knowledge',
    'jiangsu_query',
    'report',
    'chart',
    'board',
    'ops',
    'smart_inspection',
    'operations_analysis',
    'device_control',
    'station_fault_diagnosis'
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

test('agent platform icons use distinct semantic silhouettes', () => {
  const iconSignatures = AGENT_MODES.map(agent => agent.iconPaths.join('|'))
  assert.equal(new Set(iconSignatures).size, AGENT_MODES.length)

  const query = AGENT_MODES.find(agent => agent.id === 'query')
  const chart = AGENT_MODES.find(agent => agent.id === 'chart')
  assert.match(query.iconPaths.join(' '), /c0 1\.7 3\.1 3 7 3s7-1\.3 7-3/)
  assert.match(chart.iconPaths.join(' '), /m5 16 4-5 4 3 6-8/)
})

test('every agent provides complete chat welcome content', () => {
  assert.equal(AGENT_MODES.length, 14)
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

test('agent platform selects the project-declared modes without leaking another project selection', () => {
  assert.deepEqual(selectAgentModes(AGENT_MODE_IDS).map(agent => agent.id), AGENT_MODE_IDS)
  assert.deepEqual(
    selectAgentModes(['query', 'expert', 'report', 'chart']).map(agent => agent.id),
    ['query', 'expert', 'report', 'chart']
  )
})

test('project overrides turn query mode into the Jiangxi query-and-chart agent', () => {
  const [query] = selectAgentModes(['query'], {
    query: {
      name: '智能问数生图智能体',
      description: '查询噪声数据、生成图表与统计分析',
      tags: ['噪声查询', '图表生成'],
      welcome: {
        description: '查询江西省噪声监测数据',
        features: ['查询噪声数据', '生成可视化图表']
      }
    }
  })

  assert.equal(query.name, '智能问数生图智能体')
  assert.equal(query.description, '查询噪声数据、生成图表与统计分析')
  assert.deepEqual(query.tags, ['噪声查询', '图表生成'])
  assert.deepEqual(query.welcome.features, ['查询噪声数据', '生成可视化图表'])
})

test('default platform scenes cover every shared agent exactly once', () => {
  const sceneModeIds = AGENT_SCENES.flatMap(scene => scene.modeIds)
  assert.equal(new Set(sceneModeIds).size, AGENT_MODE_IDS.length)
  assert.deepEqual([...sceneModeIds].sort(), [...AGENT_MODE_IDS].sort())
})
