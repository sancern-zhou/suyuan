import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { test } from 'node:test'

import { loadProjectBuildConfig } from './projectManifest.mjs'


const repoRoot = resolve(import.meta.dirname, '../..')


test('default project enables core and legacy', () => {
  const config = loadProjectBuildConfig({ projectId: 'default', repoRoot })

  assert.equal(config.project, 'default')
  assert.deepEqual(config.modules, ['core', 'legacy'])
  assert.deepEqual(config.frontend, { theme: 'default', features: {} })
})


test('unsafe project identifiers fail before file access', () => {
  assert.throws(
    () => loadProjectBuildConfig({ projectId: '../secret', repoRoot }),
    /invalid project identifier/
  )
})
