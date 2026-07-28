import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createProjectConfig } from './projectConfig.js'


test('project config exposes module and feature predicates', () => {
  const config = createProjectConfig({
    schemaVersion: 1,
    project: 'demo',
    modules: ['core', 'noise'],
    frontend: { theme: 'demo', features: { noiseMap: true } }
  })

  assert.equal(config.hasModule('noise'), true)
  assert.equal(config.hasModule('atmosphere'), false)
  assert.equal(config.hasFeature('noiseMap'), true)
  assert.equal(config.hasFeature('missing'), false)
})
