import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync } from 'node:fs'
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
    agentSceneOverrides: {},
    agentPlatformLayout: 'scenes',
    agentScenes: [],
    sidebarAgentModes: ['query'],
    platformGuide: null
  })
})

test('platform guide accepts scene-grouped modes with full data rows', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  platform_guide:',
    '    intro: 演示平台简介',
    '    mode_groups:',
    '    - scene: office',
    '      modes:',
    '      - name: 助手',
    '        desc: 通用办公助手',
    '        example: 帮我写一份通知',
    '    - scene: monitoring',
    '      scene_name: 监测分析',
    '      modes:',
    '      - name: 问数',
    '        desc: 查询数据并生成图表',
    '        example: 查本月达标天数',
    '    mode_motto: 先选模式再提问',
    '    data_groups:',
    '    - title: 演示数据',
    '      rows:',
    '      - name: 演示指标',
    '        granularity: 日',
    '        range: 2026-01-01 至今',
    '        sync: 每日同步',
    '        desc: 演示用指标说明',
    '    notices:',
    '    - 结论附带统计口径',
    '    - 结论标注数据截至时间'
  ].join('\n'))

  const guide = loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }).frontend.platformGuide

  assert.equal(guide.intro, '演示平台简介')
  assert.deepEqual(guide.modeGroups.map(group => group.scene), ['office', 'monitoring'])
  assert.equal(guide.modeGroups[0].sceneName, '')
  assert.equal(guide.modeGroups[1].sceneName, '监测分析')
  assert.deepEqual(guide.modeGroups[0].modes[0], { name: '助手', desc: '通用办公助手', example: '帮我写一份通知' })
  assert.equal(guide.modeMotto, '先选模式再提问')
  assert.deepEqual(guide.dataGroups[0].rows[0], {
    name: '演示指标',
    granularity: '日',
    range: '2026-01-01 至今',
    sync: '每日同步',
    desc: '演示用指标说明'
  })
  assert.deepEqual(guide.notices, ['结论附带统计口径', '结论标注数据截至时间'])
})

test('platform guide accepts flat usage modes instead of scene groups', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  platform_guide:',
    '    mode_motto: 先选模式再提问',
    '    usage_modes:',
    '    - name: 问数',
    '      desc: 查询数据并生成图表',
    '      example: 查本月达标天数',
    '    data_groups:',
    '    - title: 演示数据',
    '      rows:',
    '      - name: 演示指标',
    '        desc: 演示用指标说明'
  ].join('\n'))

  const config = loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot })
  const guide = config.frontend.platformGuide

  assert.deepEqual(guide.usageModes.map(mode => mode.name), ['问数'])
  assert.equal(guide.modeMotto, '先选模式再提问')
  assert.deepEqual(guide.dataGroups[0].rows[0], {
    name: '演示指标',
    granularity: '',
    range: '',
    sync: '',
    desc: '演示用指标说明'
  })
  assert.deepEqual(guide.notices, [])
})

test('platform guide rejects scene groups combined with flat modes', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  platform_guide:',
    '    mode_groups:',
    '    - scene: office',
    '      modes:',
    '      - name: 助手',
    '        desc: 通用办公助手',
    '        example: 帮我写一份通知',
    '    usage_modes:',
    '    - name: 问数',
    '      desc: 查询数据并生成图表',
    '      example: 查本月达标天数'
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /cannot declare both mode_groups and usage_modes/
  )
})

test('platform guide mode group must reference a known scene', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  platform_guide:',
    '    mode_groups:',
    '    - scene: parking',
    '      modes:',
    '      - name: 助手',
    '        desc: 通用办公助手',
    '        example: 帮我写一份通知'
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /must be a known agent scene id/
  )
})


test('xuchang project enables only its declared business modules', () => {
  const config = loadProjectBuildConfig({ projectId: 'xuchang', repoRoot })

  assert.deepEqual(config.modules, ['core', 'legacy', 'satellite', 'xuchang-air-quality', 'xuchang-satellite'])
  assert.deepEqual(config.frontend.agentModes, ['assistant', 'query', 'knowledge', 'expert', 'report'])
  assert.equal(config.frontend.defaultAgentMode, 'query')
  assert.equal(config.frontend.agentPlatformLayout, 'scenes')
  assert.deepEqual(config.frontend.agentScenes, ['monitoring'])
  assert.deepEqual(config.frontend.agentSceneOverrides, {
    monitoring: { modeIds: ['assistant', 'query', 'knowledge', 'expert', 'report'] }
  })
  assert.deepEqual(config.frontend.sidebarAgentModes, [])
})

test('jiangxi project uses the reduced noise interface', () => {
  const config = loadProjectBuildConfig({ projectId: 'jiangxi', repoRoot })

  assert.equal(config.project, 'jiangxi')
  assert.equal(config.frontend.brandName, '江西省噪声智能分析平台')
  assert.deepEqual(config.frontend.agentModes, ['query', 'expert', 'report'])
  assert.equal(config.frontend.defaultAgentMode, 'query')
  assert.equal(config.frontend.agentModeOverrides.query.name, '智能问数生图智能体')
  assert.equal(config.frontend.agentModeOverrides.query.tags.includes('图表生成'), true)
  assert.equal(config.frontend.agentPlatformLayout, 'environment-grid')
})


test('unsafe project identifiers fail before file access', () => {
  assert.throws(
    () => loadProjectBuildConfig({ projectId: '../secret', repoRoot }),
    /invalid project identifier/
  )
})

test('unknown agent scene ids fail validation', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  agent_scenes: [parking]',
    ''
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /unknown agent scene/
  )
})

test('sidebar agent modes must be declared agent modes', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  agent_modes: [query]',
    '  sidebar_agent_modes: [query, expert]',
    ''
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /must be declared in frontend\.agent_modes/
  )
})

test('unknown agent scene override ids fail validation', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  agent_scene_overrides:',
    '    parking:',
    '      mode_ids: [query]',
    ''
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /unknown agent scene override/
  )
})

test('agent scene override mode ids must reference known modes', () => {
  const tempRoot = resolve(import.meta.dirname, '../../../tmp/opencode/manifest-test')
  mkdirSync(resolve(tempRoot, 'projects/demo'), { recursive: true })
  mkdirSync(resolve(tempRoot, 'modules'), { recursive: true })
  writeFileSync(resolve(tempRoot, 'projects/demo/project.yaml'), [
    'schema_version: 1',
    'project: demo',
    'frontend:',
    '  agent_scene_overrides:',
    '    monitoring:',
    '      mode_ids: [query, parking]',
    ''
  ].join('\n'))

  assert.throws(
    () => loadProjectBuildConfig({ projectId: 'demo', repoRoot: tempRoot }),
    /unknown agent mode/
  )
})
