import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { test } from 'node:test'

import { loadProjectBuildConfig } from './projectManifest.mjs'


const repoRoot = resolve(import.meta.dirname, '../..')


test('default project enables core and legacy', () => {
  const config = loadProjectBuildConfig({ projectId: 'default', repoRoot })

  assert.equal(config.project, 'default')
  assert.deepEqual(config.modules, ['core', 'legacy'])
  assert.deepEqual(config.frontend, {
    theme: 'default',
    brandName: '风清气智',
    features: {},
    agentModes: ['assistant', 'ppt', 'expert', 'query', 'report', 'chart', 'board', 'ops'],
    defaultAgentMode: 'assistant',
    agentModeOverrides: {},
    agentPlatformLayout: 'scenes',
    coordinator: null
  })
})


test('xuchang project enables only its declared business modules', () => {
  const config = loadProjectBuildConfig({ projectId: 'xuchang', repoRoot })

  assert.deepEqual(config.modules, ['core', 'legacy', 'satellite', 'xuchang-air-quality', 'xuchang-satellite'])
  assert.deepEqual(config.frontend.agentModes, ['query', 'expert', 'report', 'chart'])
  assert.equal(config.frontend.defaultAgentMode, 'query')
  assert.equal(config.frontend.agentPlatformLayout, 'environment-grid')
})

test('jiangsu operations project exposes its dedicated operations modes', () => {
  const config = loadProjectBuildConfig({ projectId: 'jiangsu-ops', repoRoot })
  assert.deepEqual(config.frontend.agentModes, [
    'ops', 'jiangsu_query', 'expert', 'smart_inspection', 'operations_analysis',
    'device_control', 'station_fault_diagnosis'
  ])
  assert.equal(config.frontend.defaultAgentMode, 'ops')
  assert.equal(config.frontend.agentModeOverrides.jiangsu_query.name, '江苏问数生图智能体')
  assert.equal(config.frontend.agentModeOverrides.jiangsu_query.tags.includes('问数生图'), true)
})


test('jiangxi project uses the reduced noise interface', () => {
  const config = loadProjectBuildConfig({ projectId: 'jiangxi', repoRoot })

  assert.equal(config.project, 'jiangxi')
  assert.equal(config.frontend.brandName, '江西省噪声智能分析平台')
  assert.deepEqual(config.frontend.agentModes, ['query', 'expert', 'report', 'chart'])
  assert.equal(config.frontend.defaultAgentMode, 'query')
  assert.equal(config.frontend.agentPlatformLayout, 'environment-grid')
})


test('unsafe project identifiers fail before file access', () => {
  assert.throws(
    () => loadProjectBuildConfig({ projectId: '../secret', repoRoot }),
    /invalid project identifier/
  )
})
