import assert from 'node:assert/strict'
import test from 'node:test'

import { createAuthFetch, gatewayUrl } from './http.js'


function sessionStorage() {
  return {
    readSession: () => ({ token: 'company-token', sysCode: 'SUYUAN' }),
    clearCalls: 0,
    clear() { this.clearCalls += 1 }
  }
}


test('internal API paths receive the gateway prefix and company headers', async () => {
  const seen = []
  const storage = sessionStorage()
  const authFetch = createAuthFetch({
    storage,
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async (url, options) => {
      seen.push({ url, options })
      return new Response('{}', { status: 200 })
    }
  })
  const form = new FormData()
  form.append('file', new Blob(['data']), 'data.txt')

  await authFetch('/api/upload/chat', { method: 'POST', body: form })

  assert.equal(seen[0].url, '/api/suyuan/upload/chat')
  assert.equal(seen[0].options.headers.get('Authorization'), 'Bearer company-token')
  assert.equal(seen[0].options.headers.get('SysCode'), 'SUYUAN')
  assert.equal(seen[0].options.body, form)
  assert.equal(seen[0].options.headers.has('Content-Type'), false)
})


test('gateway prefixes are not duplicated', () => {
  assert.equal(gatewayUrl('/api/suyuan/info', '/api/suyuan'), '/api/suyuan/info')
  assert.equal(gatewayUrl('/api/info?x=1', '/api/suyuan'), '/api/suyuan/info?x=1')
})


test('401 clears the session while 403 preserves it', async () => {
  const storage = sessionStorage()
  const statuses = [401, 403]
  const authFetch = createAuthFetch({
    storage,
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async () => new Response('{}', { status: statuses.shift() })
  })

  await authFetch('/api/one')
  await authFetch('/api/two')

  assert.equal(storage.clearCalls, 1)
})


test('a delayed 401 from an old token preserves a newer session', async () => {
  let token = 'old-token'
  const storage = {
    readSession: () => ({ token, sysCode: 'SUYUAN' }),
    clearCalls: 0,
    clear() { this.clearCalls += 1 }
  }
  const authFetch = createAuthFetch({
    storage,
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async () => {
      token = 'new-token'
      return new Response('{}', { status: 401 })
    }
  })

  await authFetch('/api/old-session-request')

  assert.equal(storage.clearCalls, 0)
  assert.equal(token, 'new-token')
})


test('an optional request can preserve the session on 401', async () => {
  const storage = sessionStorage()
  const authFetch = createAuthFetch({
    storage,
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async () => new Response('{}', { status: 401 })
  })

  await authFetch('/api/optional-configuration', { clearOnUnauthorized: false })

  assert.equal(storage.clearCalls, 0)
})


test('explicit signed-public and external requests never receive the company token', async () => {
  const seen = []
  const authFetch = createAuthFetch({
    storage: sessionStorage(),
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async (url, options) => {
      seen.push({ url, headers: options.headers })
      return new Response('{}', { status: 200 })
    }
  })

  await authFetch('/api/signed-media/file?signature=x', { public: true })
  await authFetch('https://example.test/data', { external: true })

  assert.equal(seen[0].url, '/api/suyuan/signed-media/file?signature=x')
  assert.equal(seen[0].headers.has('Authorization'), false)
  assert.equal(seen[1].url, 'https://example.test/data')
  assert.equal(seen[1].headers.has('Authorization'), false)
})


test('absolute external URLs require an explicit opt-in', async () => {
  const authFetch = createAuthFetch({
    storage: sessionStorage(),
    fetchImpl: async () => new Response('{}', { status: 200 })
  })

  await assert.rejects(() => authFetch('https://example.test/data'), /external: true/)
})
