import assert from 'node:assert/strict'
import test from 'node:test'

import {
  companyRuntimeConfig,
  initializeAuthStore,
  loadAuthRuntimeConfig,
  normalizeAuthRuntimeConfig
} from './runtimeConfig.js'


const mockPayload = {
  authMode: 'mock',
  sysCode: 'SUYUAN',
  mockUser: {
    id: 'local-developer',
    userName: 'local-developer',
    name: '本地开发用户',
    roleCodes: ['SUYUAN_ADMIN'],
    isAdmin: true,
    sysCode: 'SUYUAN',
    authSource: 'mock'
  }
}


test('loads mock mode from the public business-gateway endpoint without credentials', async () => {
  const calls = []
  const config = await loadAuthRuntimeConfig({
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return new Response(JSON.stringify(mockPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    }
  })

  assert.deepEqual(config, mockPayload)
  assert.deepEqual(calls, [{
    url: '/api/suyuan/auth/runtime-config',
    options: { cache: 'no-store', credentials: 'same-origin' }
  }])
})


test('invalid, unknown, and unavailable runtime config fail closed to company mode', async () => {
  assert.deepEqual(normalizeAuthRuntimeConfig({ authMode: 'disabled' }), companyRuntimeConfig())
  assert.deepEqual(
    normalizeAuthRuntimeConfig({ authMode: 'mock', mockUser: { id: '' } }),
    companyRuntimeConfig()
  )
  assert.deepEqual(
    await loadAuthRuntimeConfig({ fetchImpl: async () => { throw new Error('offline') } }),
    companyRuntimeConfig()
  )
})


test('initializes the auth store with the loaded runtime config', async () => {
  const seen = []
  const authStore = { configure: config => seen.push(config) }

  const config = await initializeAuthStore(authStore, {
    load: async () => mockPayload
  })

  assert.deepEqual(config, mockPayload)
  assert.deepEqual(seen, [mockPayload])
})
