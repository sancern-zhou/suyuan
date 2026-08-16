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
      agentPlatformLayout: 'coordinator',
      coordinator: {
        name: '小助',
        stationImageUrl: '/project-assets/demo/station.png',
        quickPrompts: [{ label: '查数据', prompt: '查询今天数据', mode: 'query' }],
        attentionTaskIds: ['task-1'],
        routes: [{ mode: 'query', keywords: ['查询'] }]
      }
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
  assert.equal(config.agentPlatformLayout, 'coordinator')
  assert.equal(config.coordinator.name, '小助')
  assert.equal(config.coordinator.stationImageUrl, '/project-assets/demo/station.png')
  assert.equal(config.coordinator.quickPrompts[0].mode, 'query')
})
