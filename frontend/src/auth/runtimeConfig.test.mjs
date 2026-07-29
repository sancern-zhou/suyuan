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
  assert.equal(calls[0].url, '/api/suyuan/auth/runtime-config')
  assert.equal(calls[0].options.cache, 'no-store')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[0].options.signal instanceof AbortSignal, true)
})


test('invalid, unknown, and unavailable runtime config fail closed to company mode', async () => {
  const invalidMockPayloads = [
    { authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'x', isAdmin: true } },
    { ...mockPayload, sysCode: '' },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, userName: '' } },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, name: '  ' } },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, roleCodes: ['viewer'] } },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, roleCodes: ['SUYUAN_ADMIN', 1] } },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, authSource: 'company' } },
    { ...mockPayload, mockUser: { ...mockPayload.mockUser, sysCode: 'OTHER' } }
  ]

  assert.deepEqual(normalizeAuthRuntimeConfig({ authMode: 'disabled' }), companyRuntimeConfig())
  for (const payload of invalidMockPayloads) {
    assert.deepEqual(normalizeAuthRuntimeConfig(payload), companyRuntimeConfig())
  }
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


test('aborts a stalled runtime config request and fails closed to company mode', async () => {
  let aborted = false
  const config = await loadAuthRuntimeConfig({
    timeoutMs: 5,
    fetchImpl: async (url, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        aborted = true
        reject(options.signal.reason)
      }, { once: true })
    })
  })

  assert.equal(aborted, true)
  assert.deepEqual(config, companyRuntimeConfig())
})
