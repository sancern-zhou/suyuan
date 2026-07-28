import assert from 'node:assert/strict'
import { test } from 'node:test'

import { filterProjectRoutes } from './projectRoutes.js'


test('routes without a requirement and enabled module routes remain', () => {
  const routes = [
    { path: '/login' },
    { path: '/air', meta: { requiredModule: 'atmosphere' } },
    { path: '/noise', meta: { requiredModule: 'noise' } }
  ]

  assert.deepEqual(
    filterProjectRoutes(routes, moduleId => moduleId === 'noise').map(route => route.path),
    ['/login', '/noise']
  )
})
