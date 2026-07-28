import assert from 'node:assert/strict'
import { test } from 'node:test'

import { filterSidebarModules } from './sidebarProjectModules.js'


test('sidebar excludes modules owned by disabled business modules', () => {
  const modules = [
    { id: 'new-task' },
    { id: 'air-map', requiredModule: 'atmosphere' },
    { id: 'noise-map', requiredModule: 'noise' }
  ]

  assert.deepEqual(
    filterSidebarModules(modules, moduleId => moduleId === 'noise').map(item => item.id),
    ['new-task', 'noise-map']
  )
})
