import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createProjectConfig } from './projectConfig.js'


test('project config exposes module and feature predicates', () => {
  const config = createProjectConfig({
    schemaVersion: 1,
    project: 'demo',
    modules: ['core', 'noise'],
    frontend: {
      theme: 'demo',
      brandName: '演示项目',
      features: { noiseMap: true, era5HistoricalBackfill: false },
      agentModes: ['assistant', 'query'],
      defaultAgentMode: 'query',
      agentPlatformLayout: 'scenes',
      agentScenes: ['monitoring'],
      agentSceneOverrides: { monitoring: { modeIds: ['query', 'assistant'] } },
      sidebarAgentModes: ['query', 'knowledge']
    }
  })

  assert.equal(config.hasModule('noise'), true)
  assert.equal(config.hasModule('atmosphere'), false)
  assert.equal(config.hasFeature('noiseMap'), true)
  assert.equal(config.hasFeature('missing'), false)
  assert.equal(config.isFeatureEnabled('era5HistoricalBackfill', true), false)
  assert.equal(config.isFeatureEnabled('unspecified', true), true)
  assert.equal(config.brandName, '演示项目')
  assert.deepEqual(config.agentModeIds, ['assistant', 'query'])
  assert.equal(config.defaultAgentMode, 'query')
  assert.equal(config.agentPlatformLayout, 'scenes')
  assert.deepEqual(config.agentScenes, ['monitoring'])
  assert.deepEqual(config.agentSceneOverrides, { monitoring: { modeIds: ['query', 'assistant'] } })
  assert.deepEqual(config.sidebarAgentModes, ['query', 'knowledge'])
  assert.equal(config.platformGuide, null)
})

test('project config freezes platform guide content', () => {
  const config = createProjectConfig({
    schemaVersion: 1,
    project: 'demo',
    modules: ['core'],
    frontend: {
      theme: 'demo',
      brandName: '演示项目',
      features: {},
      agentModes: ['assistant'],
      defaultAgentMode: 'assistant',
      agentPlatformLayout: 'scenes',
      agentScenes: ['office'],
      agentSceneOverrides: {},
      sidebarAgentModes: [],
      platformGuide: {
        intro: '演示平台简介',
        modeMotto: '先选模式再提问',
        modeGroups: [
          { scene: 'office', sceneName: '', modes: [{ name: '助手', desc: '通用办公助手', example: '帮我写一份通知' }] }
        ],
        usageModes: [],
        dataGroups: [
          {
            title: '演示数据',
            rows: [{ name: '演示指标', granularity: '日', range: '2026-01-01 至今', sync: '每日同步', desc: '演示用指标说明' }]
          }
        ],
        notices: ['结论附带统计口径']
      }
    }
  })

  const guide = config.platformGuide
  assert.equal(guide.intro, '演示平台简介')
  assert.equal(guide.modeMotto, '先选模式再提问')
  assert.equal(guide.modeGroups[0].sceneName, '')
  assert.equal(guide.modeGroups[0].modes[0].name, '助手')
  assert.equal(guide.dataGroups[0].rows[0].sync, '每日同步')
  assert.deepEqual(guide.notices, ['结论附带统计口径'])
  assert.throws(() => { guide.notices.push('新增须知') })
  assert.throws(() => { guide.dataGroups[0].rows[0].name = '改动' })
})
